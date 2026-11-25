"""Double-entry engine. Every posting is balanced, immutable, idempotent per business event, and refused inside a closed period."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.core.exceptions import BusinessRuleViolation
from apps.procurement.models import next_number

from .models import Account, DailyClose, Expense, JournalEntry, JournalLine, ZERO

A = Account.Type
CHART = [
    ("1000", "Cash on hand", A.ASSET), ("1010", "Mobile money & payment gateway clearing", A.ASSET), ("1020", "Bank", A.ASSET),
    ("1100", "Accounts receivable", A.ASSET), ("1150", "Staff salary advances", A.ASSET), ("1200", "Inventory", A.ASSET),
    ("2000", "Accounts payable (suppliers)", A.LIABILITY), ("2100", "Sales tax payable", A.LIABILITY),
    ("2200", "Customer prepayments (online orders)", A.LIABILITY), ("2250", "Customer refunds payable", A.LIABILITY),
    ("2300", "Salaries payable", A.LIABILITY), ("2310", "Payroll tax payable", A.LIABILITY), ("2320", "Pension contributions payable", A.LIABILITY),
    ("2330", "Other payroll deductions payable", A.LIABILITY),
    ("3000", "Owner's equity", A.EQUITY), ("3100", "Opening balances / retained earnings", A.EQUITY),
    ("4000", "Sales revenue", A.REVENUE), ("4100", "Delivery fee revenue", A.REVENUE),
    ("4900", "Sales discounts (contra revenue)", A.REVENUE), ("4950", "Sales returns & refunds (contra revenue)", A.REVENUE),
    ("5000", "Cost of goods sold", A.EXPENSE), ("5100", "Inventory write-offs & adjustments", A.EXPENSE),
    ("6000", "Salaries & wages", A.EXPENSE), ("6100", "Rent", A.EXPENSE), ("6200", "Utilities", A.EXPENSE), ("6300", "Transport & delivery", A.EXPENSE),
    ("6400", "Marketing", A.EXPENSE), ("6500", "Licences & compliance", A.EXPENSE), ("6900", "Other operating expenses", A.EXPENSE),
    ("6950", "Cash over / short", A.EXPENSE), ("6960", "Bank & payment fees", A.EXPENSE),
]
COST_OF_SALES = ("5000", "5100")


def q2(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ensure_chart() -> None:
    """Idempotent: also adds accounts introduced by later releases to pharmacies that already have a chart."""
    if Account.objects.filter(is_system=True).count() >= len(CHART):
        return
    for code, name, typ in CHART:
        Account.objects.get_or_create(code=code, defaults={"name": name, "type": typ, "is_system": True})


def account_map() -> dict[str, Account]:
    ensure_chart()
    return {a.code: a for a in Account.objects.all()}


def pay_account(method: str) -> str:
    if method.startswith("cash"):  # cash, cash_on_pickup, cash_on_delivery
        return "1000"
    return { "mobile_money": "1010", "monime": "1010", "card": "1020", "bank_transfer": "1020", "bank": "1020"}.get(method, "1020")


def last_closed_date():
    c = DailyClose.objects.order_by("-date").first()
    return c.date if c else None


def post_entry(*, description, lines, source_type, source_id="", date=None, user=None, branch=None, reverses=None) -> JournalEntry | None:
    """lines: iterable of (account_code, debit, credit[, branch][, memo]). Returns None when there is nothing to post (all zero)."""
    source_id = str(source_id or "")
    if source_id:
        existing = JournalEntry.objects.filter(source_type=source_type, source_id=source_id).first()
        if existing:
            return existing  # idempotent: the same business event never posts twice
    date = date or timezone.localdate()
    closed = last_closed_date()
    if closed and date <= closed:
        raise BusinessRuleViolation(f"The period up to {closed} is closed. Nothing can be posted into it.")
    accounts = account_map()
    norm = []
    for ln in lines:
        code, debit, credit = ln[0], q2(ln[1] or 0), q2(ln[2] or 0)
        line_branch = ln[3] if len(ln) > 3 and ln[3] is not None else branch
        memo = ln[4] if len(ln) > 4 else ""
        if debit < 0 or credit < 0 or (debit > 0 and credit > 0):
            raise ValidationError({"lines": "Each line must have exactly one positive amount (debit or credit)."})
        if debit == 0 and credit == 0:
            continue
        acc = accounts.get(code)
        if acc is None or not acc.is_active:
            raise ValidationError({"lines": f"Account {code} is not available."})
        norm.append((acc, line_branch, debit, credit, memo))
    if not norm:
        return None
    total_d, total_c = sum(n[2] for n in norm), sum(n[3] for n in norm)
    if total_d != total_c or len(norm) < 2:
        raise BusinessRuleViolation(f"Unbalanced journal entry (debits {total_d} vs credits {total_c}). Nothing was posted.")
    with transaction.atomic():
        e = JournalEntry.objects.create(number=next_number("JE"), date=date, description=description[:300], source_type=source_type, source_id=source_id,
                                        total=total_d, reverses=reverses, created_by=user)
        for acc, b, d, c, memo in norm:
            JournalLine.objects.create(entry=e, account=acc, branch=b, debit=d, credit=c, memo=memo[:200])
    return e


# ---------------- manual journals, reversals ----------------
@transaction.atomic
def post_manual(*, user, description, lines, date=None, idempotency_key="") -> JournalEntry:
    if not description.strip():
        raise ValidationError({"description": "A description is required."})
    if date and date > timezone.localdate():
        raise ValidationError({"date": "Entries cannot be dated in the future."})
    e = post_entry(description=description, lines=lines, source_type="manual", source_id=f"manual:{idempotency_key}" if idempotency_key else "", date=date, user=user)
    if e is None:
        raise ValidationError({"lines": "Enter amounts."})
    audit.record("accounting.manual_entry", actor=user, target=e, number=e.number, total=str(e.total))
    return e


REVERSIBLE = {"manual", "expense"}  # system-sourced entries are corrected through their business process (returns, refunds, write-offs)


@transaction.atomic
def reverse_entry(entry_id, *, user, reason) -> JournalEntry:
    e = JournalEntry.objects.select_for_update(of=("self",)).get(pk=entry_id)
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required."})
    if e.source_type not in REVERSIBLE:
        raise BusinessRuleViolation("This entry was posted automatically. Correct it through the related return, refund or adjustment.")
    if hasattr(e, "reversed_by"):
        raise BusinessRuleViolation("This entry has already been reversed.")
    lines = [(l.account.code, l.credit, l.debit, l.branch_id and l.branch, l.memo) for l in e.lines.select_related("account", "branch")]
    rev = post_entry(description=f"Reversal of {e.number}: {reason}", lines=lines, source_type="reversal", source_id=f"rev:{e.pk}", user=user, reverses=e)
    if e.source_type == "expense":
        Expense.objects.filter(journal_entry=e).update(status=Expense.Status.REVERSED)
    audit.record("accounting.entry_reversed", actor=user, target=e, reversal=rev.number, reason=reason)
    return rev


# ---------------- expenses ----------------
@transaction.atomic
def create_expense(*, user, date, account, amount, payment_method, description, branch=None, vendor="", reference="") -> Expense:
    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if account.type != Account.Type.EXPENSE or not account.is_active or account.code in COST_OF_SALES:
        raise ValidationError({"account": "Choose an active operating expense category."})
    if payment_method not in ("cash", "bank", "mobile_money"):
        raise ValidationError({"payment_method": "Choose cash, bank or mobile money."})
    if date > timezone.localdate():
        raise ValidationError({"date": "Expenses cannot be dated in the future."})
    if not description.strip():
        raise ValidationError({"description": "A description is required."})
    exp = Expense.objects.create(date=date, branch=branch, account=account, amount=amount, payment_method=payment_method, vendor=vendor[:150],
                                 reference=reference[:100], description=description[:300], created_by=user)
    e = post_entry(description=f"Expense: {description}", lines=[(account.code, amount, 0, branch), (pay_account(payment_method), 0, amount, branch)],
                   source_type="expense", source_id=str(exp.pk), date=date, user=user)
    exp.journal_entry = e
    exp.save(update_fields=["journal_entry", "updated_at"])
    audit.record("accounting.expense_recorded", actor=user, target=exp, branch_id=branch.pk if branch else None, amount=str(amount), account=account.code)
    return exp


# ---------------- accounts ----------------
@transaction.atomic
def create_account(*, user, code, name, type_) -> Account:
    ensure_chart()
    if type_ not in {t.value for t in Account.Type}:
        raise ValidationError({"type": "Unknown account type."})
    if not code.isdigit() or not 4 <= len(code) <= 6:
        raise ValidationError({"code": "Use a numeric code of 4-6 digits."})
    prefix = {"asset": "1", "liability": "2", "equity": "3", "revenue": "4", "expense": "56"}[type_]
    if code[0] not in prefix:
        raise ValidationError({"code": f"{type_.title()} accounts must start with {' or '.join(prefix)}."})
    if Account.objects.filter(code=code).exists():
        raise ValidationError({"code": "This account code is already in use."})
    a = Account.objects.create(code=code, name=name.strip()[:120], type=type_)
    audit.record("accounting.account_created", actor=user, target=a, code=code)
    return a


# ---------------- daily close ----------------
@transaction.atomic
def close_day(*, user, date) -> DailyClose:
    from . import reports
    if date >= timezone.localdate():
        raise BusinessRuleViolation("Only past days can be closed.")
    last = last_closed_date()
    if last and date <= last:
        raise BusinessRuleViolation(f"Books are already closed through {last}.")
    tb = reports.trial_balance(as_of=date)
    if not tb["balanced"]:
        raise BusinessRuleViolation("The trial balance does not balance; the day cannot be closed.")
    day = reports.income_statement(date_from=date, date_to=date)
    cash = reports.cash_flow(date_from=date, date_to=date)
    summary = {"net_revenue": str(day["net_revenue"]), "net_profit": str(day["net_profit"]), "expenses": str(day["operating_expenses_total"]),
               "cash_net_change": str(cash["net_change"]), "closing_cash": str(cash["closing_cash"]), "entries": JournalEntry.objects.filter(date=date).count()}
    c = DailyClose.objects.create(date=date, closed_by=user, summary=summary)
    audit.record("accounting.day_closed", actor=user, target=c, date=str(date))
    return c

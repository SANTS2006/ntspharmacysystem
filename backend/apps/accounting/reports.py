"""Read-only financial reports computed from the ledger (the single source of truth)."""
from decimal import Decimal

from django.db.models import Count, F, Sum

from .engine import COST_OF_SALES, account_map
from .models import Account, JournalEntry, JournalLine, ZERO

CASH_CODES = ("1000", "1010", "1020")


def _lines(date_from=None, date_to=None, branch_id=None):
    qs = JournalLine.objects.all()
    if date_from:
        qs = qs.filter(entry__date__gte=date_from)
    if date_to:
        qs = qs.filter(entry__date__lte=date_to)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return qs


def _by_account(qs):
    return {r["account__code"]: (r["account__name"], r["account__type"], r["d"] or ZERO, r["c"] or ZERO)
            for r in qs.values("account__code", "account__name", "account__type").annotate(d=Sum("debit"), c=Sum("credit"))}


def _net(typ, d, c):
    return d - c if typ in ("asset", "expense") else c - d


def trial_balance(as_of=None, branch_id=None):
    account_map()
    rows, td, tc = [], ZERO, ZERO
    for code, (name, typ, d, c) in sorted(_by_account(_lines(None, as_of, branch_id)).items()):
        bal = d - c
        debit, credit = (bal, ZERO) if bal > 0 else (ZERO, -bal)
        rows.append({"code": code, "name": name, "type": typ, "debit": debit, "credit": credit})
        td, tc = td + debit, tc + credit
    return {"as_of": as_of, "rows": rows, "total_debit": td, "total_credit": tc, "balanced": td == tc}


def income_statement(date_from=None, date_to=None, branch_id=None):
    data = _by_account(_lines(date_from, date_to, branch_id))
    revenue = [{"code": c, "name": n, "amount": _net(t, d, cr)} for c, (n, t, d, cr) in sorted(data.items()) if t == "revenue"]
    cos = [{"code": c, "name": n, "amount": _net(t, d, cr)} for c, (n, t, d, cr) in sorted(data.items()) if c in COST_OF_SALES]
    opex = [{"code": c, "name": n, "amount": _net(t, d, cr)} for c, (n, t, d, cr) in sorted(data.items()) if t == "expense" and c not in COST_OF_SALES]
    net_revenue, cos_total, opex_total = sum((r["amount"] for r in revenue), ZERO), sum((r["amount"] for r in cos), ZERO), sum((r["amount"] for r in opex), ZERO)
    gross = net_revenue - cos_total
    return {"date_from": date_from, "date_to": date_to, "revenue": revenue, "net_revenue": net_revenue, "cost_of_sales": cos, "cost_of_sales_total": cos_total,
            "gross_profit": gross, "operating_expenses": opex, "operating_expenses_total": opex_total, "net_profit": gross - opex_total}


def balance_sheet(as_of=None, branch_id=None):
    data = _by_account(_lines(None, as_of, branch_id))
    section = lambda typ: [{"code": c, "name": n, "amount": _net(t, d, cr)} for c, (n, t, d, cr) in sorted(data.items()) if t == typ]  # noqa: E731
    assets, liabilities, equity = section("asset"), section("liability"), section("equity")
    earnings = sum((_net("revenue", d, c) for _, (_, t, d, c) in data.items() if t == "revenue"), ZERO) - sum((_net("expense", d, c) for _, (_, t, d, c) in data.items() if t == "expense"), ZERO)
    ta, tl, te = sum((x["amount"] for x in assets), ZERO), sum((x["amount"] for x in liabilities), ZERO), sum((x["amount"] for x in equity), ZERO)
    return {"as_of": as_of, "assets": assets, "liabilities": liabilities, "equity": equity, "current_earnings": earnings, "total_assets": ta, "total_liabilities": tl,
            "total_equity": te + earnings, "balanced": ta == tl + te + earnings}


def cash_flow(date_from=None, date_to=None, branch_id=None):
    base = _lines(None, None, branch_id).filter(account__code__in=CASH_CODES)
    opening = ZERO
    if date_from:
        o = base.filter(entry__date__lt=date_from).aggregate(d=Sum("debit"), c=Sum("credit"))
        opening = (o["d"] or ZERO) - (o["c"] or ZERO)
    period = base
    if date_from:
        period = period.filter(entry__date__gte=date_from)
    if date_to:
        period = period.filter(entry__date__lte=date_to)
    rows = {}
    for r in period.values("entry__source_type").annotate(d=Sum("debit"), c=Sum("credit")):
        rows[r["entry__source_type"]] = {"source": r["entry__source_type"], "inflow": r["d"] or ZERO, "outflow": r["c"] or ZERO}
    for r in rows.values():  # money moving between cash/bank/mobile money nets to zero in a single entry
        r["net"] = r["inflow"] - r["outflow"]
    net = sum((r["net"] for r in rows.values()), ZERO)
    return {"date_from": date_from, "date_to": date_to, "opening_cash": opening, "by_source": sorted(rows.values(), key=lambda x: x["source"]), "net_change": net, "closing_cash": opening + net,
            "accounts": [c for c in CASH_CODES]}


def general_ledger(code, date_from=None, date_to=None, branch_id=None, limit=500):
    acc = account_map().get(code)
    if acc is None:
        return None
    before = _lines(None, None, branch_id).filter(account=acc)
    opening = ZERO
    if date_from:
        o = before.filter(entry__date__lt=date_from).aggregate(d=Sum("debit"), c=Sum("credit"))
        opening = _net(acc.type, o["d"] or ZERO, o["c"] or ZERO)
    qs = _lines(date_from, date_to, branch_id).filter(account=acc).select_related("entry").order_by("entry__date", "entry__id", "id")[:limit]
    running, rows = opening, []
    for l in qs:
        running += _net(acc.type, l.debit, l.credit)
        rows.append({"date": l.entry.date, "entry": l.entry.number, "description": l.entry.description, "source": l.entry.source_type, "debit": l.debit, "credit": l.credit, "balance": running})
    return {"account": {"code": acc.code, "name": acc.name, "type": acc.type}, "opening_balance": opening, "lines": rows, "closing_balance": running, "truncated": len(rows) == limit}


def branch_summary(date_from=None, date_to=None):
    from apps.tenants.models import Branch
    names = {b.pk: b.name for b in Branch.objects.all()}
    out = []
    for bid in [None, *names]:
        qs = _lines(date_from, date_to).filter(branch__isnull=True) if bid is None else _lines(date_from, date_to, bid)
        data = _by_account(qs)
        rev = sum((_net(t, d, c) for _, (_, t, d, c) in data.items() if t == "revenue"), ZERO)
        cos = sum((_net(t, d, c) for code, (_, t, d, c) in data.items() if code in COST_OF_SALES), ZERO)
        exp = sum((_net(t, d, c) for code, (_, t, d, c) in data.items() if t == "expense" and code not in COST_OF_SALES), ZERO)
        if bid is None and not data:
            continue
        out.append({"branch": bid, "name": names.get(bid, "Pharmacy level"), "net_revenue": rev, "cost_of_sales": cos, "gross_profit": rev - cos, "operating_expenses": exp, "net_profit": rev - cos - exp})
    return out


def receivables():
    from apps.sales.models import Sale
    ledger = _by_account(_lines().filter(account__code="1100")).get("1100")
    open_sales = Sale.objects.filter(status="partially_paid").values("id", "reference_number", "customer_name", "total", "amount_paid")
    return {"ledger_balance": (ledger[2] - ledger[3]) if ledger else ZERO,
            "open_sales": [{**s, "balance": s["total"] - s["amount_paid"]} for s in open_sales]}


def payables():
    from apps.procurement.services import supplier_balances
    ledger = _by_account(_lines().filter(account__code="2000")).get("2000")
    return {"ledger_balance": (ledger[3] - ledger[2]) if ledger else ZERO, "supplier_invoices_outstanding": supplier_balances(),
            "note": "Ledger payables follow goods received; supplier invoices may differ if suppliers bill different amounts."}


def integrity():
    bad = list(JournalEntry.objects.annotate(d=Sum("lines__debit"), c=Sum("lines__credit")).exclude(d=F("c")).values("number", "d", "c"))
    tb = trial_balance()
    return {"entries": JournalEntry.objects.count(), "unbalanced_entries": bad, "trial_balance_balanced": tb["balanced"], "total_debit": tb["total_debit"], "total_credit": tb["total_credit"]}

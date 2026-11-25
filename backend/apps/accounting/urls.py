from django.urls import path

from . import views as v

urlpatterns = [
    path("accounting/accounts/", v.AccountsView.as_view()),
    path("accounting/accounts/<int:pk>/", v.AccountDetailView.as_view()),
    path("accounting/journal-entries/", v.JournalView.as_view()),
    path("accounting/journal-entries/<int:pk>/", v.JournalDetailView.as_view()),
    path("accounting/journal-entries/<int:pk>/reverse/", v.ReverseView.as_view()),
    path("accounting/expenses/", v.ExpensesView.as_view()),
    path("accounting/expenses/<int:pk>/reverse/", v.ReverseExpenseView.as_view()),
    path("accounting/closes/", v.CloseView.as_view()),
    path("accounting/reports/trial-balance/", v.TrialBalanceView.as_view()),
    path("accounting/reports/income-statement/", v.IncomeStatementView.as_view()),
    path("accounting/reports/balance-sheet/", v.BalanceSheetView.as_view()),
    path("accounting/reports/cash-flow/", v.CashFlowView.as_view()),
    path("accounting/reports/general-ledger/<str:code>/", v.GeneralLedgerView.as_view()),
    path("accounting/reports/branch-summary/", v.BranchSummaryView.as_view()),
    path("accounting/reports/receivables/", v.ReceivablesView.as_view()),
    path("accounting/reports/payables/", v.PayablesView.as_view()),
    path("accounting/reports/integrity/", v.IntegrityView.as_view()),
]

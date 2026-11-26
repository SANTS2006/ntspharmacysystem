# NTS Pharmacy System: UI design system

## Where things live
- Tokens and component classes: `frontend/src/index.css` (emerald primary `#059669`, navy `#142D3D`, Inter, self-hosted through `@fontsource-variable/inter` so the CSP needs no external font host).
- Shared components: `frontend/src/components/ui/` (PageHeader, StatCard, BarList, StatusBadge, Pagination, Modal, EmptyState, ErrorState, Loading, PageBoundary, `useConfirm`, `usePrompt`, `useToast`).
- Application shell (staff and platform areas): `frontend/src/components/layout/AppShell.tsx`.
- Sign-in family: `frontend/src/components/auth/AuthUi.tsx`.

## Classes to use in new pages
`page-title`, `section-title`, `field-label`, `card`, `table-wrap` + `table`, `btn` + `btn-primary | btn-secondary | btn-outline | btn-danger | btn-sm`, `btn-link`, `badge-*`, `alert alert-*`, `tablist` + `tab` / `tab-active`, `empty`, `skeleton`.
Inputs, selects and textareas are styled globally. Never use `window.prompt` or `window.confirm`: use the dialog hooks.

## Branding
The staff and platform areas use the system palette. Each pharmacy's public website uses that pharmacy's own colour, logo and name.

## Gaps (documented, not invented)
- No customer directory or patient profile screen. The API has `/patients/` (used inside Prescriptions), but there is no purchase-history endpoint per patient.
- Header search jumps between pages only: there is no cross-record search API.
- The notification bell shows stock alerts from `/inventory/alerts/`: there is no general notifications API.
- No "my profile" edit endpoint; the user menu offers Change password and Sign out.
- The access token is held in memory, so reloading the browser tab asks the user to sign in again (behaviour unchanged by the redesign).
- Some module pages (HR, payroll, accounting, procurement, engagement) have the new styling but keep their original page structure and inline forms; their tables are not individually paginated or searchable unless they already were.

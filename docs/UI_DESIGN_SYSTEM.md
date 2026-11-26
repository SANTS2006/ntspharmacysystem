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

## Themes, motion and layout
Light and dark themes are token-based (`.dark` on `<html>`, applied before paint by `public/theme.js`). Page content takes 90% of its area
(`page-wrap`, `site-wrap`). Websites use `components/site/motion.tsx` (reveal on scroll, tilt cards, slide-in menu, page SEO) and a lazy-loaded
three.js scene (`components/three/`). All motion is disabled for reduced-motion users.

## Shared building blocks
`FormModal`/`FormFields` (add and edit dialogs with placeholders, password toggle, colour picker), `useConfirm` (delete and other confirmations),
`DataTable`/`ServerTable` (search, sort, pagination), `Loading`/`TableLoader`/`PageLoader` (branded loaders), `components/charts`.
Staff modules and their required permissions are listed once in `pages/tenant/access.ts`.

## Gaps (documented, not invented)
- "Delete" for medicines, branches, suppliers, services, staff and customers deactivates or archives, so sales and clinical history are kept. Only
  categories without medicines, notifications, saved addresses and profile pictures are permanently deleted.
- Header search jumps between pages only: there is no cross-record search API.
- The access token stays in memory; after a reload the session is renewed from the tab's refresh token.

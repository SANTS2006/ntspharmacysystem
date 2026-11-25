# Prescription Workflow

`received` -> `under_review` (pharmacist starts review; safety checks run) -> `approved` (pharmacist confirms prescriber, patient and dosage checks and has
recorded a decision on every critical alert) -> `partially_dispensed` / `dispensed`. Side exits: `rejected` (reason), `cancelled` (reason), `expired` (derived
when the validity date passes). Refills reset the dispensing counters for a new cycle while keeping every dispensing record.

**Authorization.** Registration needs `prescription.register` (pharmacist, technician, branch manager, admin). Review/approve/reject/interventions need
`prescription.verify`, dispensing/refill `prescription.dispense` (pharmacist and, by default, pharmacy admin; remove these from the admin role if the admin is not a
pharmacist). Cashiers have none. Uploading an image changes nothing about the status: dispensing is impossible before pharmacist approval.

**Dispensing.** All-or-nothing; stock is taken FEFO from saleable batches only (expired/recalled/quarantined/damaged never dispense), movements are logged as `dispense`
with the prescription reference. Safety checks are re-run immediately before dispensing; open critical alerts block it. Controlled medicines additionally write an
immutable `ControlledDrugRegisterEntry` (patient, prescriber, batch, quantity, balance after, pharmacist).

**Safety checks (rule-based, system output only).** Allergy match against patient allergies entered by staff (critical), duplicate therapy (inside the prescription and
against the patient's other active prescriptions), interactions from the pharmacy's OWN interaction table, pharmacy-recorded contraindication text (info) and a
pregnancy flag when contraindication text mentions pregnancy. Alerts are labelled `source: system`; the pharmacist's decision is stored separately (note, who, when).
No clinical data is bundled or invented. **Not implemented:** age and dosage-range rules, medicine-history review across dispensings, integration with any licensed drug database.

**Privacy.** Documents are stored under `MEDIA_ROOT` and never served by a public URL; downloads go through an authorized, audited endpoint (PDF/PNG/JPG/WebP, magic-byte
checked, 5 MB cap, `nosniff`, `no-store`). Reading a prescription detail is audited. Branch-scoped staff see only their branch's prescriptions and patients.

**Not yet implemented.** Linking a dispensing to payment and receipt (Phase 7 POS fills `Dispensing.sale_id`), patient/customer-facing upload and refill requests (Phase 8),
prescription retention/regulatory reporting configuration, notification emails/real-time updates (Phase 9), document encryption at rest and R2 storage (Phase 13), editing items on a registered prescription (cancel and re-register).

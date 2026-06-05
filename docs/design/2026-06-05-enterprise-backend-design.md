# Enterprise Backend Foundation — Design

**Date:** 2026-06-05
**Status:** Approved (Spec 1 of enterprise-grade program)
**Repo:** tb-face_attendance (`~/frappe-bench/apps/face_attendance`); no tb-facecore changes.

## Context

First of four specs making the face-attendance product enterprise-grade and sellable
(custom B2B app, self-deployed on Frappe bench, tightly coupled to HRMS):

1. **Enterprise backend foundation** — this spec
2. Employee portal overhaul (mobile-first SPA at `/face`)
3. HR admin dashboard SPA
4. Market-gap features (mobile GPS check-in, geofencing, shift-policy engine) — future

Competitor research: `docs/research/2026-06-05-competitor-benchmark.md`. Findings driving
this spec: privacy-by-design messaging sells in India (DPDP Act 2023); device fleet health
is an under-marketed differentiator; dashboards/APIs are table stakes.

MVP tracking scope: attendance events only (check-in/out, last-seen, on-premises status).
No zone tracking, no video object tracking, no kiosk, no hospitality mode.

## Current state (relevant)

- DocTypes: Employee Face Profile (workflow: Draft → Pending → Approved/Rejected),
  Face Edge Device, Face Recognition Event, Face Recognition Settings (Single)
- `api.py`: `get_face_data` (role-gated sync), `post_event` (dedup via unique constraint),
  `heartbeat`, `get_device_status`
- `portal.py`: `get_my_status`, `register_face`, `submit_for_approval`, `verify_me`
  (rate-limited)
- Jobs: `check_stale_devices` (hourly, flips status only), `ping_embedding_service`
- Report: Face Profiles Needing Reenrollment

## Section 1 — Compliance (consent, retention, deletion)

### Consent capture

- New fields on **Employee Face Profile**: `consent_given` (Check), `consent_on`
  (Datetime), `consent_text_version` (Data)
- **Face Recognition Settings**: `consent_text` (Text Editor), `consent_version` (Data)
- `register_face` requires a `consent: 1` parameter; rejects without it. Stamps
  `consent_on` = now, `consent_text_version` = settings version
- Portal shows consent text before capture (Spec 2 wires the UI; API enforces now)

### Consent withdrawal / revocation

- New workflow state **Revoked** on Employee Face Profile (reachable from Approved
  and Pending)
- New portal endpoint `revoke_my_consent`: employee self-revokes → workflow → Revoked,
  embedding cleared, enrollment image Files deleted
- Re-enrollment after revocation allowed: Revoked joins Draft/Rejected as a
  re-capture state (fresh consent required)
- Device sync already filters `workflow_state = Approved`, so revoked profiles drop from
  edge devices on next sync automatically

### Auto-offboarding

- `doc_events` hook on **Employee** `on_update`: when status becomes Left (or
  relieving date set), auto-revoke the face profile (same purge path as withdrawal)
- No orphaned biometrics of ex-employees

### Retention

- **Face Recognition Settings**: `event_retention_days` (Int, default 365)
- Daily scheduler job purges Face Recognition Events older than cutoff.
  Employee Checkins are untouched (HR records); events are sensor logs
- `user_data_fields` in hooks.py covering Employee Face Profile and Face Recognition
  Event → Frappe's built-in personal data export/anonymize handles DPDP/GDPR requests

### Audit

- `track_changes: 1` on Employee Face Profile and Face Edge Device

## Section 2 — Dashboard & portal data APIs

All HR endpoints gated `frappe.only_for(["HR Manager", "System Manager"])`; portal
endpoints resolve own employee via `user_id` (existing pattern). New module
`dashboard.py` for HR endpoints to keep `api.py` edge-only.

- `get_attendance_summary` — today: present/absent/late counts (late vs shift start
  where employee has a Shift Assignment), per-employee first-in/last-out
- `get_live_events` — recent Face Recognition Events with employee name + photo,
  device, scores, time; cursor pagination (`before` param, limit ≤ 50)
- Realtime: `publish_realtime("face_attendance_event", …)` after event insert in
  `post_event` → dashboards subscribe via socketio, no polling
- `get_approval_queue` — pending profiles with employee details + enrollment image URL
- `approve_profile(name)` / `reject_profile(name, reason)` — wrap `apply_workflow`;
  rejection reason stored (new field `rejection_reason` on profile) and shown to employee
- `get_enrollment_stats` — enrolled / pending / rejected / revoked / not-enrolled counts
  vs active Employee total
- `get_device_status` — extend each row with `events_7d` (per-day counts for sparkline)
- `get_my_status` — extend with current-month summary: days present, average in-time

## Section 3 — Notifications & monitoring

- `check_stale_devices` extended: on transition to Unreachable, create a System
  Notification + email to users with HR Manager role (throttled: once per outage,
  not hourly re-alerts)
- Profile submitted for approval → notify HR Manager users
- Approved/Rejected → notify the employee (email; portal shows state already)
- Daily digest (Settings toggle `send_daily_digest`, default off): yesterday's
  attendance summary emailed to HR Manager role
- Consistent `frappe.log_error` on edge-path failures

Implementation: Frappe Notification documents as fixtures where declarative works
(workflow-state notifications); Python for the device-outage alert (needs throttle logic).

## Section 4 — Enterprise polish

- **Workspace** "Face Attendance" (fixture): shortcuts to the 4 DocTypes + reports;
  number cards: enrolled, pending approval, devices online; charts: events/day,
  enrollment funnel
- **Roles**: keep existing split (HR Manager / Employee / Face Edge Device);
  document the permission matrix in app docs
- **Tests**: frappe tests for every new endpoint, retention job, offboarding hook,
  consent enforcement, revocation purge
- **Capacity doc**: publish per-edge throughput and per-server scale numbers in docs
  (competitors cite specs; we should too)

## Error handling

- Consent missing → `frappe.throw` with clear message (400)
- Revocation purge is transactional: workflow transition + embedding clear + file
  delete in one request; failure rolls back whole action
- Retention job logs deleted count; failures → Error Log, next run retries naturally
- Notification failures never block the triggering transaction (wrap in try/except +
  log; Frappe email queue already async)

## Testing

Existing 27-test suite stays green. New coverage:
- consent: register without consent fails; with consent stamps fields
- revocation: embedding + files purged, state Revoked, sync excludes profile
- offboarding: Employee → Left revokes profile
- retention: old events deleted, recent kept, checkins untouched
- dashboard endpoints: permission gates (Employee role gets 403), pagination, counts
- notifications: outage alert fires once per outage

## Out of scope

Mobile GPS check-in, geofencing, shift-policy engine, payroll export, kiosk mode,
hospitality/guest verification, zone tracking, model upgrades in facecore, UI work
(Specs 2–3).

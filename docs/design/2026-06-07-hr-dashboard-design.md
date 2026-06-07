# HR Admin Dashboard — Design (Spec 3)

**Date:** 2026-06-07
**Repo:** tb-face_attendance (`~/frappe-bench/apps/face_attendance`)
**Scope:** Admin section inside the existing `/face` SPA (`frontend/`). One additive
backend endpoint. Lands via GitHub PR.

## Goal

Give HR Managers a live operational dashboard: today's attendance at a glance,
realtime recognition feed, face-profile approval queue, and edge-device health —
without leaving the `/face` SPA.

## Decisions (locked with user)

| Topic | Decision |
|---|---|
| Mount | Same SPA, nested `/admin` routes (no second frontend app) |
| Views | Overview, Live feed, Approvals, Devices |
| Realtime | socket.io subscribe `face_attendance_event`; fallback 30s poll |
| Role gate | New `get_dashboard_context` endpoint (`{is_hr}`); APIs already server-gated |
| Landing | Feature branch → conventional commits → `gh pr create` → `gh pr merge` |

## Architecture

Nested route group `/admin` with `AdminLayout` parent component: wider container
(`max-w-5xl`), horizontal section nav (Overview / Live / Approvals / Devices),
"← My portal" link back to employee Home. Employee bottom tabs hidden under
`/admin` (route meta). Employee shell shows an "Admin" nav entry only when
`is_hr` is true.

### File structure (frontend, all under `frontend/src/`)

```
composables/useDashboardContext.js   singleton resource for get_dashboard_context
components/admin/AdminLayout.vue     wide shell + section nav + route guard
components/admin/StatCard.vue        number + label card (overview stats)
components/admin/Sparkline.vue       tiny inline 7-bar SVG (device events_7d)
pages/admin/Overview.vue             stat cards, enrollment funnel, today table,
                                     pending-approvals banner
pages/admin/LiveFeed.vue             realtime event list + load-more
pages/admin/Approvals.vue            approval queue cards + approve/reject dialog
pages/admin/Devices.vue              device health cards
```

`router.js` gains a nested `/admin` route with the four children, all
`meta: { fullScreen: true, admin: true }` (hides employee header/tabs;
AdminLayout provides its own chrome). `App.vue` container width becomes
meta-driven: `max-w-5xl` when `route.meta.admin`, else `max-w-lg`.

### Backend (additive)

`face_attendance/dashboard.py`:

```python
@frappe.whitelist(methods=["GET"])
def get_dashboard_context():
    roles = set(frappe.get_roles())
    return {"is_hr": bool(roles & {"HR Manager", "System Manager"})}
```

Plus tests (HR user → true, plain employee → false). Nothing else — all data
APIs shipped in Spec 1.

### APIs consumed (existing)

| Endpoint | View |
|---|---|
| `dashboard.get_attendance_summary` | Overview (counts + employee table) |
| `dashboard.get_enrollment_stats` | Overview funnel |
| `dashboard.get_approval_queue` / `approve_profile` / `reject_profile` | Approvals |
| `dashboard.get_live_events` (keyset `next_before`) | Live feed |
| `api.get_device_status` | Devices |
| realtime `face_attendance_event` (published per HR user) | Live feed |

## Views

### Overview (`/admin`)

- 4 StatCards: Present, Absent, Late, Total active (from attendance summary).
- Pending-approvals banner when `enrollment_stats.pending > 0` → links to Approvals.
- Enrollment funnel: horizontal segmented bar (approved/pending/draft/rejected/
  revoked/not-enrolled) with legend counts.
- Today table: employee, first in, last out, Late badge. Mobile: rows collapse to
  two-line cards.

### Live feed (`/admin/live`)

- Newest-first list: employee avatar (image or initials), name, device, time
  (HH:MM:SS), similarity + liveness scores.
- Realtime: socket.io subscription to `face_attendance_event`; on event, reload
  first page (single API call; avoids duplicating enrichment logic client-side).
- Socket unavailable → 30s polling of first page. Indicator dot shows
  live/polling mode.
- "Load more" appends next page via `next_before` cursor.

### Approvals (`/admin/approvals`)

- Card per pending profile: enrollment image, employee name + ID, det_score,
  liveness_score, consent date, waiting-since (modified).
- Approve: confirm dialog → `approve_profile` → remove card, refresh stats.
- Reject: dialog with required reason textarea → `reject_profile(name, reason)`.
- Empty state: "No pending approvals."

### Devices (`/admin/devices`)

- Card per device: name, status badge (Online green / Offline red by status
  field), location, last seen, app version, events today, 7-day Sparkline.

## Cross-cutting

- Role guard: AdminLayout checks `useDashboardContext`; while loading → skeleton;
  `is_hr` false → redirect `/`. Server remains the real gate.
- HR user without Employee record: `get_my_status` throws — employee Home shows
  friendly error state; admin section works independently (does not depend on
  useStatus).
- Loading: SkeletonCard per section. Errors: ErrorMessage + retry. Empty states
  designed.
- All list/load-more requests respect server limit cap (50).

## Testing & verification

- Backend: tests for `get_dashboard_context` (2). Existing 63 stay green.
- Frontend: `yarn build` exit 0 per task; manual walkthrough (admin nav hidden for
  plain employee, live feed updates on recognition event, approve/reject round-trip,
  device cards).
- Landing: PR with summary + test results; GitHub merge (Verified).

## Out of scope

Attendance date-range reports/exports, zone tracking, kiosk mode, GPS check-in
(Spec 4), notifications UI, multi-site fleet view.

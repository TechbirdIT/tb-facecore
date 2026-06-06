# Employee Portal Overhaul — Design (Spec 2)

**Date:** 2026-06-06
**Repo:** tb-face_attendance (`~/frappe-bench/apps/face_attendance/frontend`)
**Scope:** Pure frontend. No backend changes — consumes APIs shipped in Spec 1.

## Goal

Rebuild the `/face` employee SPA as a mobile-first, native-feeling app: bottom tab
navigation, guided consent-first registration wizard, attendance history with month
summary, profile with consent record and revoke-consent flow.

## Decisions (locked with user)

| Topic | Decision |
|---|---|
| Structure | Home + bottom tab bar (Home / History / Profile); wizard + self-test full-screen |
| Registration | 4-step consent-first wizard: Consent → Capture → Review → Done |
| Submission | Auto-submit for approval after enrollment (chain `register_face` → `submit_for_approval`) |
| History | Month summary stat cards + day-grouped check-in list |
| Revoke | Profile danger zone, full-screen confirm, type `REVOKE` to enable button |
| Design language | frappe-ui native + Tailwind, polished mobile spacing; no new component deps |
| Self-test | Action card on Home, opens full-screen flow |
| PWA | Out of scope (revisit in Spec 4 with mobile GPS check-in) |

## Architecture

Approach: rebuild structure, reuse plumbing. Keep `main.js`, vite/build config
(`yarn build` → `--base=/assets/face_attendance/frontend/` → copy `www/face.html`),
`createWebHistory("/face")`. Replace `App.vue` shell, replace pages, enhance
`CameraCapture.vue`.

### File structure

```
frontend/src/
├─ main.js                      (unchanged)
├─ App.vue                      shell: header + router-view + BottomTabs (hidden on full-screen routes)
├─ router.js                    routes: / /history /profile /register /self-test
├─ composables/useStatus.js     shared get_my_status resource (single fetch, shared across tabs)
├─ components/
│  ├─ BottomTabs.vue            3 tabs, active state, safe-area inset
│  ├─ CameraCapture.vue         enhanced: oval face-guide overlay, capture hints
│  ├─ StatusCard.vue            enrollment state badge + contextual CTA
│  ├─ CheckinList.vue           day-grouped check-in rows (reused Home today + History)
│  └─ SkeletonCard.vue          loading placeholder
└─ pages/
   ├─ Home.vue                  status card, today's check-ins, self-test action card
   ├─ History.vue               month summary cards + day-grouped list
   ├─ Profile.vue               employee info, enrollment, consent record, danger zone
   ├─ RegisterWizard.vue        4-step full-screen wizard
   ├─ RevokeConfirm.vue         full-screen revoke confirmation
   └─ SelfTest.vue              full-screen capture → match result
```

Old `pages/Register.vue`, `pages/Status.vue` deleted.

### APIs consumed (all existing)

| Endpoint | Method | Used by |
|---|---|---|
| `face_attendance.portal.get_my_status` | GET | useStatus → all tabs (profile, checkins 30d, month summary, employee info) |
| `face_attendance.portal.register_face` | POST `{image_base64, consent: 1}` | wizard step 4 |
| `face_attendance.portal.submit_for_approval` | POST | wizard step 4 (chained) |
| `face_attendance.portal.revoke_my_consent` | POST | RevokeConfirm |
| `face_attendance.portal.verify_me` | POST `{image_base64}` | SelfTest |

`get_my_status` must expose consent fields (`consent_on`, `consent_text_version`) and
settings consent text for the wizard. If missing from current response, the consent
text is fetched via a small addition to `get_my_status` — the ONLY permitted backend
touch, additive read-only fields.

## Components & flows

### Home (`/`)

- **StatusCard** — state-driven:
  - no profile → "Not enrolled" + CTA **Register your face** → `/register`
  - Draft → "Enrollment incomplete" + CTA **Continue registration** → `/register`
  - Pending Approval → "Awaiting HR approval" (info, no CTA)
  - Rejected → rejection reason + CTA **Re-register** → `/register`
  - Revoked → "Consent revoked" + CTA **Register again** → `/register`
  - Approved → green "Active" + enrolled date
- **Today's check-ins** — filter 30-day checkins to today, IN/OUT rows; empty state.
- **Self-test card** — visible only when Approved; → `/self-test`.

### Registration wizard (`/register`)

Full-screen, no tab bar. Step indicator dots, back arrow (step > 1 → previous step;
step 1 → Home).

1. **Consent** — scrollable consent text (from settings) + policy version; if state
   Rejected, rejection reason banner on top. Checkbox "I agree" enables Continue.
2. **Capture** — CameraCapture with oval guide overlay + hints (good light, look
   straight, no mask). Capture button.
3. **Review** — photo, Retake / Looks good.
4. **Submit** — spinner while `register_face` then `submit_for_approval`; success
   screen "Awaiting HR approval" + Done → Home. Error: friendly message + Retry,
   stays on step (if `register_face` succeeded but `submit_for_approval` failed,
   retry only submits approval — guard via local flag).

Route guard: redirect to Home unless state in {none, Draft, Rejected, Revoked}.
(Fixes current bug: Revoked missing from re-capture list.)

### History (`/history`)

- "This month" summary cards: days present, avg in-time — from month-summary API.
- "Last 30 days" day-grouped list: date header, IN/OUT pairs with time + device.
  Empty state.
- No month picker: backend serves current-month summary + 30-day checkins only;
  a picker over that data would be a fake affordance. Revisit if history-range
  API lands later.

### Profile (`/profile`)

- Employee card: name, employee ID, department.
- Enrollment section: state badge, enrolled on, model version, stale-model warning.
- Consent record: "Consented on <date> · policy <version>" (hidden if none).
- Danger zone (visible when state Approved or Pending Approval):
  red-outlined card → **Revoke consent & delete biometric data** → `/profile/revoke`.

### Revoke confirm (`/profile/revoke`)

Full-screen. Consequences list (biometric data permanently deleted, face check-in
stops, re-registration requires new consent + HR approval). Text input: type
`REVOKE` to enable confirm button. Calls `revoke_my_consent` → success screen →
Home (StatusCard now shows Register CTA). Error → message + retry.

### Self-test (`/self-test`)

Full-screen capture (reuses CameraCapture) → posts to self-test endpoint → result
card: match/no-match + similarity score + hint when no-match. Done → Home.

## Cross-cutting

- **Loading:** SkeletonCard placeholders for every auto resource.
- **Empty states:** icon + one-line hint.
- **Errors:** frappe-ui ErrorMessage + retry affordance; raw tracebacks never shown.
- **Auth:** Frappe session; 403/401 → redirect `/login?redirect-to=/face`.
- **Mobile:** max-w-lg centered on desktop; bottom tabs with safe-area inset
  (`env(safe-area-inset-bottom)`); touch targets ≥44px.
- **Shared status:** one `useStatus` composable; tabs reload it after mutations
  (wizard done, revoke done).

## Testing & verification

- No backend changes (except possible additive fields in `get_my_status` — covered
  by extending existing portal tests if touched).
- `cd frontend && yarn build` must pass clean.
- Existing backend suite stays green (61 tests).
- Manual mobile-viewport walkthrough: register (each state entry), revoke, history,
  self-test, empty/error states.

## Out of scope

PWA/offline, GPS check-in, geofencing (Spec 4); HR dashboard SPA (Spec 3);
backend API changes beyond additive `get_my_status` fields.

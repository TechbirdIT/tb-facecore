# Design: Presence Sessions & Hours Worked (per Area)

**Status:** Draft for review — no code written yet
**Audience:** everyone (written in plain English; a technical appendix is at the end)
**Decision owner:** _[your name]_
**Last updated:** 2026-06-11

---

## 1. What we're trying to do (in one paragraph)

We want the cameras to answer two questions for each employee:
1. **Did they show up?** (clock-in)
2. **How long were they actually present in a given area** (a floor, a room, a workstation), across the day?

And we want the "how long" number to be **fair** — stepping out of camera view for a moment, or walking between rooms, must **not** punish the employee.

---

## 2. How it works today (and why there are no attendance hours yet)

Today the flow is:

```
Camera recognises a face  ─►  "Recognition Event" is saved  ─►  an "Employee Checkin" is created
   (edge device)                 (audit record)                    (handed to HRMS)
```

When a check-in is created, the HR system (HRMS) **automatically decides whether it is an "IN" or an "OUT"** by simply *flipping* from the last one: first sighting = IN, next = OUT, next = IN, and so on.

**Why you see no Attendance hours on the system right now:**
HRMS only turns check-ins into an **Attendance record with hours** if three things are set up: (a) work **Shifts** are defined, (b) each employee is **assigned** to a shift, and (c) **"Auto Attendance"** is switched on and the background scheduler runs. None of that is configured on the bench yet — so check-ins are being recorded, but nothing is adding them up into hours. That's expected, not a bug.

---

## 3. Why the "IN / OUT flip" is the wrong tool for us

You spotted the core problem. Because IN/OUT just *alternates*, this happens:

- Employee is at their desk. Camera sees them. → **IN**
- They lean out of view to grab a folder. Camera loses them, then sees them again 20 seconds later. → **OUT**, then **IN** again.

The system now thinks they *left and came back* — and on a multi-floor site with people moving between rooms and two cameras occasionally seeing the same person, this produces nonsense hours (e.g. "worked 12 seconds"). **It is unfair and unreliable for your situation.** So we will **not** use IN/OUT flipping to measure presence.

---

## 4. The new idea: **Presence Sessions** (the heart of this design)

Think of a **security guard with a notepad**. Every so often they glance up and jot down: *"9:01 — saw Martin at Desk 3. 9:02 — still there. 9:03 — still there…"* When Martin disappears for a while, the guard draws a line and closes that block of time. If Martin pops out for 30 seconds and comes back, the guard doesn't start a new block — it's obviously the same continuous presence.

That's exactly what we'll build, automatically:

- Each glance is a **Sighting** (the camera recognised the employee — this is the *"number of times tracked"* you described).
- A run of nearby sightings is stitched into one **Presence Session** (a continuous "they were here" block).
- **Hours worked = the total length of those blocks.**

> **Important refinement on your point #3:** counting *how many times* someone was tracked isn't quite enough on its own — 500 sightings could mean 1 busy hour or 8 quiet hours. The magic ingredient is the **time stamp on each sighting**. We keep your "count the sightings" idea, and simply attach a clock to each one so we can measure the *length* of each presence block. (Good news: we already record every sighting with a timestamp today — the "Recognition Event" — so the foundation is already there.)

---

## 5. The rules, in plain English

A few simple, tunable rules decide how sightings become hours. Sensible starting values are shown; all are adjustable later.

| Rule | Plain meaning | Starting value |
|---|---|---|
| **Sampling rate** (a.k.a. global cooldown) | We note a person "seen" at most once every X seconds per area — not every video frame. Keeps things tidy and avoids double-counting when two cameras see the same person. | every **30 sec** |
| **Session gap (timeout)** | If we *don't* see the person for longer than this, their current presence block ends. Shorter than this = "they never really left." | **5 min** |
| **Minimum block** | Ignore tiny blips (someone walking past). A block shorter than this doesn't count. | **60 sec** |
| **Daily cap** | A safety ceiling so a stuck camera can't record 26 hours. | **e.g. 12 h** |

---

## 6. Worked example (so everyone can picture it)

Martin's morning at **Floor 2 — Open Office**:

| Time | What the camera sees | What the system does |
|---|---|---|
| 09:00 | First sighting | **Opens** a presence block (start 09:00) |
| 09:00–10:30 | Seen every ~30 sec | Keeps the block open, updates "last seen" |
| 10:30 | Steps to the printer, out of view ~2 min | Gap (2 min) is **under** 5 min → **same block**, no penalty ✅ |
| 10:32–12:00 | Seen again, continuously | Block still open |
| 12:00 | Goes to lunch, gone 45 min | Gap (45 min) is **over** 5 min → block **closes** at 12:00 |
| 12:45 | Returns | **Opens** a new block (start 12:45) |
| 12:45–17:00 | Seen continuously | Block stays open until end of day / he leaves |

**Hours on Floor 2 = (12:00 − 09:00) + (17:00 − 12:45) = 3h 00m + 4h 15m = 7h 15m.**
Lunch is correctly **not** counted. The printer trip **is** counted (he never really left). Fair. ✅

---

## 7. How this answers your specific points

- **Multi-floor / multiple rooms:** every camera belongs to an **Area**. Presence blocks are tracked **per area**, so you get "3h on Floor 2, 1h in the Lab" and a fair daily total. (Today there's only a free-text "location" on each camera; we'll turn that into a proper **Area** so several cameras can cover one area.)
- **Stepping out of frame & coming back:** handled by the **Session gap** rule — short absences keep the same block. This was your main fairness worry, and it's solved by design.
- **"Count the times tracked" as the foundation:** yes — that's exactly the Sighting stream, now with timestamps so it becomes fair hours.
- **Global cooldown:** built in as the **Sampling rate** — one sighting per person per area every ~30 sec, no matter how many cameras or frames. This also fixes the "two cameras double-count the same person" risk.
- **No reliance on HRMS IN/OUT:** our hours come from presence blocks, not flips. (If you later want the numbers to also flow into HRMS payroll/Attendance, we can generate official check-ins from each block — start = IN, end = OUT — as a *separate, optional* step. Decision for later.)

---

## 8. Your question: can multiple cameras share **one** config file?

**Today:** one camera = one `config.yaml` = one running program. To add a camera you copy the config, point it at the new camera, and run a second program.

**Can one config / one program handle several cameras? Yes — and it's a good idea.** Two ways to run things:

| Approach | Plain picture | Good | Watch out |
|---|---|---|---|
| **One program per camera** (today) | One worker watching one screen | Simple; if one crashes the others are fine | Each worker loads its own copy of the face-recognition "brain" (~300 MB + CPU) → wasteful if several run on one machine |
| **One program, many cameras** (proposed) | One worker watching several screens at once | Loads the face "brain" **once** and shares it across all its cameras → much lighter on memory | All those cameras share one machine's processing power; if that program stops, all its cameras stop |

**Recommendation:** support a **list of cameras in one config file**, so one machine can efficiently run a *handful* of nearby cameras sharing one loaded model, while you still run **separate machines** for separate locations. This is a small enhancement to the edge program; we'd document each camera in the config with its own name + area. (This is an edge-software change we'd schedule after the server-side work below.)

---

## 9. What we'll keep, change, and add (for the technical team)

**Keep**
- The edge recognition pipeline (detect → track → recognise once per track) — unchanged.
- The **Recognition Event** record — it already is our timestamped "sighting" log.

**Change**
- Edge sends a **presence sighting** for each recognised employee on a **sampling cadence** (~30 s while continuously tracked), instead of leaning on the 2-minute one-shot debounce. (Clock-in event remains a separate, once-per-arrival signal.)
- Stop using HRMS IN/OUT *alternation* as the source of "hours." (Optionally feed HRMS later from sessions.)

**Add (server-side, in the `face_attendance` Frappe app)**
1. **Area** — a record that groups cameras (devices) into a place ("Floor 2", "Lab"), with an `is_work_area` flag (corridors needn't count).
2. **Presence Session** — one row per continuous presence block: `employee`, `area`, `start_time`, `last_seen_time`, `end_time`, `sighting_count`, `status (Open/Closed)`, `duration`.
3. **Sessioniser logic** — on each incoming sighting: extend the open session for `(employee, area)` if the gap ≤ timeout, otherwise close the stale one and open a new one.
4. **"Close stale sessions" scheduled job** — runs every minute; closes any open session whose `last_seen_time` is older than the timeout (so blocks close even when a person simply vanishes).
5. **Hours report / dashboard** — hours per employee per day, per area and total.
6. **Per-employee global cooldown** — server-side guard so overlapping cameras can't double-count.

**Privacy note:** presence timelines are sensitive personal data. We should agree on **retention** (how long we keep raw sightings vs summarised daily hours) and who can view them.

---

## 10. Honest limitations (so there are no surprises)

- **Camera blind spots / downtime:** if a camera is off for 10 minutes while the employee is present, that gap may split or shorten a block (under-count). Mitigated by the existing device health monitoring and a sensible timeout.
- **"Present" ≠ "working":** the system measures *presence in an area*, not productivity. That's a policy choice to communicate to staff.
- **Wrong-person risk at scale:** with 500 faces, occasionally the system could mis-identify someone. We separately recommend **multi-frame confirmation** (only count a presence once the same face is confirmed over a few seconds) to keep sessions trustworthy.
- **Tuning is real work:** the timeout / sampling / minimum-block values will need a short tuning period with real cameras to feel fair.

---

## 11. Decisions we need from you

1. **Session gap (timeout):** 5 minutes a good "didn't really leave" window? Or 2 / 10?
2. **Do lunch/breaks count?** Current design: gaps over the timeout (e.g. lunch) are **not** counted. Agree?
3. **Areas:** what are the real areas, and which are "work areas" vs pass-through (corridors, lobbies)?
4. **HRMS link:** do you need these hours inside official HRMS Attendance/payroll, or is our own hours report enough for now?
5. **Retention & access:** how long to keep raw sightings, and who can see presence timelines?

---

## 12. Suggested build order

1. **Server-side per-employee global cooldown** (small, makes multi-camera safe immediately).
2. **Area** record + map existing cameras to areas.
3. **Presence Session** record + sessioniser + "close stale sessions" job.
4. **Hours report / dashboard.**
5. **Edge: presence sampling cadence + (optional) multiple-cameras-in-one-config.**
6. **(Optional) feed HRMS Attendance from sessions.**

Nothing here changes the camera/edge recognition we've already built — this is almost entirely **server-side**, which is correct, because the only thing that travels reliably between cameras is the **employee's identity**, not the camera's internal tracking.

---

### Technical appendix — current pipeline, precisely

- `api.py :: post_event` (role-gated to *Face Edge Device*) receives `{device_id, attendance_device_id, event_time, similarity, liveness}`, looks up the employee by `attendance_device_id`, and inserts a **Face Recognition Event** (rejecting exact-duplicate `(device, employee, event_time)` via a unique index).
- `face_recognition_event.py :: after_insert` calls HRMS `add_log_based_on_employee_field(employee_field_value=device_id, timestamp, device_id)`, which creates an **Employee Checkin**. HRMS sets `log_type` (IN/OUT) by **alternating** from the employee's previous log — this is the behaviour we are moving away from for presence.
- **No Attendance docs** appear because HRMS's auto-attendance (Shift + Shift Assignment + "Process Attendance After" + scheduler) is not configured; check-ins alone don't produce Attendance/hours.
- The proposed **Presence Session** model consumes the *same* Face Recognition Event stream but aggregates by `(employee, area)` with a gap-timeout, giving fair, area-aware hours independent of IN/OUT.

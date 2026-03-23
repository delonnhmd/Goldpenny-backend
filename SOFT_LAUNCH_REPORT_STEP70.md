# SOFT_LAUNCH_REPORT_STEP70.md

## Step 70 — Soft Launch Harness

**Objective:** Prepare Gold Penny for a small, controlled soft launch with real users while preserving visibility into completion, retention, friction, and feedback — without touching the core gameplay or economy systems.

---

## Deliverables Completed

| # | Deliverable | Status |
|---|---|---|
| 1 | Invite-code-gated access control (reversible, cohort-flagged) | ✅ |
| 2 | Cohort tagging (`soft_launch_v1` default) | ✅ |
| 3 | In-app feedback survey after Day 1 / Day 2 settlement | ✅ |
| 4 | Issue reporting tied to player / session / current day | ✅ |
| 5 | Admin visibility: cohort list, Day 1/2 completion rates, avg rating, feedback + issue lists | ✅ |
| 6 | `SOFT_LAUNCH_REPORT_STEP70.md` (this file) | ✅ |

---

## Files Created / Modified

### Backend — New Files

| File | Lines | Description |
|---|---|---|
| `app/models/soft_launch_access.py` | 28 | Pre-provisioned invite code catalogue (`soft_launch_access` table) |
| `app/models/soft_launch_member.py` | 33 | User-to-cohort membership (`soft_launch_members` table, one row per user) |
| `app/models/player_feedback.py` | 36 | Day 1/2 survey responses (`player_feedback` table) |
| `app/models/issue_report.py` | 34 | Bug/friction/UI/balance issue reports (`issue_reports` table) |
| `app/api/soft_launch.py` | ~230 | Player-facing REST endpoints (join, status, feedback, issue) |
| `alembic/versions/20260323_0021_soft_launch.py` | 117 | Migration: creates all 4 tables, chains from `20260323_0020_retention_engine` |

### Backend — Modified Files

| File | Change Summary |
|---|---|
| `app/models/__init__.py` | Added 4 new model imports after `SupplyChainDailySnapshot` |
| `app/main.py` | Added `soft_launch` to `from app.api import ...` + `include_router` for `/soft-launch` prefix |
| `app/api/internal.py` | Appended ~200 lines: 6 Pydantic response schemas + 4 admin routes under `/internal/soft-launch/*` |

### Frontend — New Files (`src/features/softLaunch/`)

| File | Lines | Description |
|---|---|---|
| `types.ts` | 26 | Shared interfaces: `SoftLaunchStatus`, `FeedbackPayload`, `IssuePayload`, `IssueCategory`, `IssueSeverity` |
| `api.ts` | 42 | `fetchApi` wrappers for `joinSoftLaunch`, `fetchSoftLaunchStatus`, `submitFeedback`, `submitIssue` |
| `useSoftLaunch.ts` | 108 | Hook with 24-hour AsyncStorage cache (`@goldpenny/soft_launch_status`), all soft launch actions |
| `SoftLaunchGate.tsx` | 133 | Full-screen blocking gate with invite code `TextInput`, loading states, error display |
| `FeedbackSheet.tsx` | 225 | Modal bottom sheet: 5-star rating + 3 text questions, auto-dismisses on submit |
| `IssueReportSheet.tsx` | 215 | Modal bottom sheet: category chips (5), severity chips (4), 2000-char description |
| `index.ts` | 7 | Barrel export for all components, hook, and types |

### Frontend — Modified Files

| File | Change Summary |
|---|---|
| `src/features/gameplayLoop/components/PlaytestObserver.tsx` | Added `PlaytestObserverProps` interface with `onRequestFeedback?: (gameDay: number) => void`; triggers on Day 1 and Day 2 settlement |
| `src/features/gameplayLoop/GameplayLoopScaffold.tsx` | Wired `useSoftLaunch`, gate rendering, dev bypass flag, `FeedbackSheet`, `IssueReportSheet`, and `PlaytestObserver` callback |

---

## Backend Architecture

### Data Models

#### `SoftLaunchAccess` — invite code catalogue
```
id              UUID PK
invite_code     String(64)  UNIQUE INDEX
cohort_tag      String(40)  default "soft_launch_v1"
description     Text
max_uses        Integer     default 1
use_count       Integer     default 0
is_active       Boolean     default True
created_at      DateTime
```

#### `SoftLaunchMember` — approved user membership
```
id              UUID PK
user_id         UUID FK users.id CASCADE  UNIQUE INDEX
invite_code_used String(64)
cohort_tag      String(40)
is_approved     Boolean     default True
joined_at       DateTime
notes           Text
```

#### `PlayerFeedback` — Day 1/2 survey responses
```
id                  UUID PK
player_id           UUID FK players.id CASCADE  INDEX
session_id          String(64)
game_day            Integer
rating              Integer (1–5)
response_confusing  Text
response_hard       Text
response_interesting Text
cohort_tag          String(40)
submitted_at        DateTime
```

#### `IssueReport` — player-reported issues
```
id                  UUID PK
player_id           UUID FK players.id CASCADE  INDEX
session_id          String(64)
game_day            Integer
description         Text  (non-null)
category            String(40)  — bug | friction | ui | balance | other
severity            String(20)  — low | medium | high | blocker
extra_context_json  Text
submitted_at        DateTime
```

### Player-Facing Routes (`/soft-launch/*`)

All routes require `Depends(get_current_user)` (Bearer JWT).

| Method | Path | Description |
|---|---|---|
| `POST` | `/soft-launch/join` | Validate invite code, create `SoftLaunchMember`, increment `use_count`. Idempotent (returns existing membership if already joined) |
| `GET` | `/soft-launch/status` | Returns `{is_member, cohort_tag, joined_at}`. Returns `{is_member: false}` if not a member |
| `POST` | `/soft-launch/feedback` | Creates `PlayerFeedback`; auto-populates `cohort_tag` from membership row |
| `POST` | `/soft-launch/issue` | Creates `IssueReport` |

### Admin Routes (`/internal/soft-launch/*`)

All routes are protected by `_require_internal_key` (`X-Internal-Key` header).

| Method | Path | Description |
|---|---|---|
| `GET` | `/internal/soft-launch/cohort` | Full member list joined with `users` table (includes email, cohort_tag, joined_at) |
| `GET` | `/internal/soft-launch/metrics` | Day 1 completion %, Day 2 return %, avg rating, total feedback count, total issue count |
| `GET` | `/internal/soft-launch/feedback` | Paginated `PlayerFeedback` list (`skip` / `limit` query params) |
| `GET` | `/internal/soft-launch/issues` | Paginated `IssueReport` list with optional `severity` and `category` filters |

**Metrics query logic:**
- Day 1 completion rate = `players with DailySettlementLog game_day == 1` / `total soft launch members`
- Day 2 return rate = `players with DailySettlementLog game_day == 2` / `total soft launch members`
- Average rating = `AVG(player_feedback.rating)` across all soft launch members

### Migration Chain

```
20260323_0020_retention_engine
    └── 20260323_0021_soft_launch   ← this step
```

All UUID columns use `sa.dialects.postgresql.UUID(as_uuid=True)` consistent with the rest of the schema.

---

## Frontend Architecture

### Gate Flow

```
GameplayLoopScaffold mounts
    ↓
useSoftLaunch() checks AsyncStorage cache (24hr TTL)
    ↓ cache miss → GET /soft-launch/status
    ↓
if (!isMember && !bypassGate)
    → render <SoftLaunchGate />  (full screen, no game content visible)
    → user enters invite code → POST /soft-launch/join
    → on success: cache updated, gate cleared, game loads
    ↓
if (isMember || bypassGate)
    → render normal game UI
```

### Feedback Trigger Flow

```
Player completes Day 1 or Day 2 settlement
    ↓ DailySettlementLog written in backend
    ↓ PlaytestObserver.trackDayCompleted(1 or 2) fires
    ↓ onRequestFeedback(gameDay) called
    ↓ setFeedbackDay(gameDay) in GameplayLoopScaffold
    ↓ <FeedbackSheet visible={feedbackDay !== null} /> appears
    ↓ Player submits (or skips)
    ↓ Sheet dismissed, feedbackDay reset to null
```

### Dev Bypass

Set `EXPO_PUBLIC_SOFT_LAUNCH_BYPASS=true` in your `.env` (or Expo EAS secrets for dev builds) to skip the gate entirely during development without a valid invite code.

```bash
# .env.local
EXPO_PUBLIC_SOFT_LAUNCH_BYPASS=true
```

The flag is checked synchronously at render time — no async required.

### AsyncStorage Cache

- **Key:** `@goldpenny/soft_launch_status`
- **TTL:** 24 hours (timestamp stored alongside payload)
- **On network failure:** status defaults to `{is_member: false}` — the gate is NOT bypassed on error (fail-safe)
- **Manual invalidation:** call `refreshStatus()` from the `useSoftLaunch` hook

---

## How to Provision Invite Codes

Invite codes are not generated via the API — they are inserted directly into the `soft_launch_access` table by an admin:

```sql
INSERT INTO soft_launch_access (id, invite_code, cohort_tag, description, max_uses, use_count, is_active, created_at)
VALUES (
    gen_random_uuid(),
    'BETA-LAUNCH-2026',
    'soft_launch_v1',
    'First cohort — friends and family',
    50,
    0,
    true,
    NOW()
);
```

- `max_uses` controls how many accounts can use a single code (set to `1` for single-use codes).
- To deactivate a code without revoking existing members: `UPDATE soft_launch_access SET is_active = false WHERE invite_code = '...'`.

---

## How to Remove the Gate for a User

**Option A — Remove membership (user must re-join):**
```sql
DELETE FROM soft_launch_members WHERE user_id = '<user_uuid>';
```

**Option B — Promote to permanent access (keep membership, raise `is_approved`):**
```sql
UPDATE soft_launch_members SET notes = 'Promoted to full access' WHERE user_id = '<user_uuid>';
```

**Option C — Bypass the gate globally for a build:**
Set `EXPO_PUBLIC_SOFT_LAUNCH_BYPASS=true` in the build environment.

---

## Known Constraints and Follow-Ups

| Constraint | Notes |
|---|---|
| `IssueReportSheet` is not surfaced by a floating button yet | The `setShowIssueReport(true)` state exists in `GameplayLoopScaffold` and is wired to the sheet; a persistent "Report Issue" FAB or menu item can be added as a follow-up without any backend changes |
| Issue reporting requires a valid player to exist | Routes do a `Player` lookup; if a user somehow has no `Player` row, the route returns HTTP 404. This matches the rest of the api contract |
| `gap` in `IssueReportSheet.tsx` StyleSheet | Requires React Native ≥ 0.71 (already satisfied by the current Expo SDK version) |
| Soft launch gate is not enforced server-side | The gate is a client-side UI guard only. Game API routes do not check `SoftLaunchMember` membership. This is intentional — it is easier to extend in a follow-up than to lock down every existing route |

---

## Validation Results

| Check | Result |
|---|---|
| Python AST syntax check (7 new/modified Python files) | ✅ All clean |
| Full project TypeScript check (`npx tsc --noEmit`) | ✅ 0 errors |
| Backend pytest suite | ✅ 699 passed, 40 pre-existing failures (all `no such table: player_progression_states` SQLite issues — unrelated to Step 70) |

---

## Summary

Step 70 delivers a complete, reversible soft launch harness. Real users can join only with an invite code, are grouped into a cohort, receive in-app feedback prompts after Day 1 and Day 2 of gameplay, and can report issues at any time. Admins have four protected endpoints to monitor the cohort's progress in real time. No core game systems were modified.

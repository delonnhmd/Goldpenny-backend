# Step 71L — Live vs Stale Log Audit

## Objective
Separate stale deployment/auth noise from the newest real onboarding failure using fresh live requests.

## Live health checks (current)
Executed against live Render URL: `https://goldpenny-backend.onrender.com`

- `GET /health` -> `200` with `{"status":"ok"}`
- `GET /health/db` -> `200` with `{"status":"database connected"}`
- `GET /docs` -> `200`
- `GET /openapi.json` -> `200`

Conclusion: backend is currently live and serving requests; DB connectivity is currently healthy for runtime checks.

## Fresh onboarding isolation
Triggered fresh request-time onboarding call (new payload each run):
- `POST /onboarding/new-player`
- Example payload shape:
  - `display_name`: `player71l_<timestamp>`
  - `gender`: `male`
  - `region`: `suburban`
  - `starter_job_code`: `retail_worker`

Observed current response (fresh request):
- `500`
- `{"detail":"Onboarding setup failed: Instance '<Player at ...>' has been deleted, or its row is otherwise not present."}`

## Log category separation
1. **Old/stale noise**
- Earlier password-auth failures can come from prior failed deploys/startup attempts or old instances.
- These are not sufficient to explain current app behavior by themselves.

2. **Current healthy runtime**
- Health endpoints and docs are live now.
- DB health endpoint succeeds now.

3. **Current real blocker (request-time)**
- Newest onboarding failure is a request-path transaction/state issue:
  - `Instance '<Player ...>' has been deleted, or its row is otherwise not present.`
- This is the active blocker for phone onboarding, not the stale auth log entries.

## Code updates made for better log isolation
- Added request trace correlation ID (`trace_id`) to `/onboarding/new-player` logs.
- Added/kept DB target+schema diagnostics so runtime DB/schema context can be verified in logs.

Files touched in this step:
- `app/api/onboarding.py`

## Recommended next fix
Focus on onboarding transaction flow (not auth):
1. Inspect `create_new_player_onboarding` rollback/recreate path after starter-init failure.
2. Ensure no stale/deleted ORM `Player` instance is reused after rollback.
3. Re-hydrate player by ID after commit before building fallback response payload.
4. Keep `trace_id` in logs to isolate a single phone retry end-to-end.

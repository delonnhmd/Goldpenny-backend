Original prompt: Step 96L — Guided Sandbox Mode

Goal
- Prevent the first 5 days from feeling directionless. Sandbox does not mean "no structure" — it means structured freedom. Each early day surfaces exactly one nudge that points the player toward the next meaningful map interaction.

Day plan
- Day 1 — get first work shift
- Day 2 — buy a meal from the map
- Day 3 — open the job board
- Day 4 — inspect a business-for-sale listing
- Day 5 — save toward first asset

Backend scope
- New service `app/services/guided_sandbox_service.py` exposes:
  - `resolve_day_nudge(player, day_number) -> {key, title, message, target_node_key, completion_hint, days_remaining}`
  - Deterministic mapping day→nudge; each nudge carries a `target_node_key` so the UI can pulse the right tile.
  - `is_active(day_number) -> bool` returns `True` for days 1–5.
- Expose via an API surface that the daily brief (or a light read-only endpoint) can consume. Brief integration is the preferred home; a dedicated endpoint is the fallback.

Frontend scope (deferred — only wire-up note in this step)
- The existing daily brief card already exists — surface the returned nudge there with a pulsing tile link.
- The map should pulse the tile matching `target_node_key` until the nudge is dismissed/completed.

Notes
- Nudges are **guidance, not gates** — the player can ignore them. After Day 5 the sandbox runs fully free.
- Keep completion detection intentionally loose in this step: presence of a matching daily action in history is enough. Tight per-day completion logic can come later if needed.

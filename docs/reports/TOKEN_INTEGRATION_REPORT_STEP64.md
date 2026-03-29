# TOKEN_INTEGRATION_REPORT_STEP64

Date: 2026-03-22  
Scope: `goldpenny-backend` (FastAPI backend) + `PFT/pft-expo/web-bridge` (Next.js bridge) + relevant mobile API client code

## Executive Summary

Step 64 goals are only partially implemented today:

- The gameplay/token boundary is mostly preserved (good).
- Wallet UI exists as a placeholder on web, and backend stores wallet addresses (partial).
- Off-chain reward accounting and claim tracking exist (good foundation).
- Secure claim architecture requirements are **not yet met** for production token payouts.

Highest-risk blockers before enabling real token transfers:

1. JWT secret can silently fall back to `"change-me"` (token forgery risk).
2. Several reward/admin endpoints are unauthenticated or only player-authenticated.
3. Claim flow is vulnerable to race-based duplicate processing (no DB-level replay lock).
4. Wallet linking has no ownership proof (no signature/nonce verification).
5. Web bridge accepts arbitrary backend host via query string, enabling server-side request forgery (SSRF).

---

## Findings (Prioritized)

### Critical

#### S64-001: Default JWT secret fallback allows trivial token forgery if env is misconfigured
- Severity: Critical
- Location:
  - `app/api/auth.py:23`
  - `app/main.py:19`
- Evidence:
  - `SECRET_KEY = os.getenv("SECRET_KEY", os.getenv("JWT_SECRET_KEY", "change-me"))`
  - `"SECRET_KEY": os.getenv("SECRET_KEY", "change-me")`
- Impact: If `SECRET_KEY` is missing, attackers can forge valid bearer tokens using a known default.
- Fix:
  - Fail startup when secret is missing or weak.
  - Enforce minimum entropy/length checks (for example, 32+ random bytes).
- Mitigation:
  - Rotate secrets immediately for all deployed environments.
  - Invalidate existing JWTs after rotation.

#### S64-002: Internal/admin reward routes are exposed without proper authorization
- Severity: Critical
- Location:
  - `app/api/rewards.py:627`
  - `app/api/rewards.py:676`
  - `app/api/rewards.py:721`
  - `app/api/rewards.py:449`
- Evidence:
  - `create_epoch(...)` and `finalize_epoch(...)` have no auth dependency.
  - `get_player_snapshots(player_id)` is directly accessible.
  - Inline note explicitly says internal/admin endpoints are currently open.
- Impact: Untrusted callers can manipulate reward epochs or read cross-player reward data.
- Fix:
  - Require admin-only auth middleware/dependency on all internal reward endpoints.
  - Move internal routes under a protected `/internal` router or service network boundary.
- Mitigation:
  - Add WAF/ingress deny rules for these paths until code-level auth is enforced.

### High

#### S64-003: Any authenticated player can trigger pool creation/closure (privilege escalation)
- Severity: High
- Location:
  - `app/api/rewards.py:395`
  - `app/api/rewards.py:421`
  - `app/api/rewards.py:406`
  - `app/api/rewards.py:437`
- Evidence:
  - `/rewards/pool/create` and `/rewards/pool/close` only require `_get_player_or_404(current_user, db)`.
  - No role/permission model exists in `app/models/user.py:10`.
- Impact: Normal players can affect global monthly reward distribution state.
- Fix:
  - Introduce role-based authorization (`admin`, `ops`) and gate pool lifecycle endpoints.
  - Add immutable audit logs for pool lifecycle actions.

#### S64-004: Wallet linking has no proof-of-ownership, yet account is marked linked
- Severity: High
- Location:
  - `app/api/rewards.py:206`
  - `app/api/rewards.py:219`
  - `app/api/rewards.py:230`
  - `app/engine/reward_engine.py:335`
- Evidence:
  - `No cryptographic signature verification is performed...`
  - `existing.is_verified = False`
  - `player.wallet_linked = True`
  - `claim_ready` uses `wallet_linked` flag, not verified wallet record.
- Impact: A user can attach arbitrary wallet addresses without proving control, creating payout-redirection risk once on-chain claims are enabled.
- Fix:
  - Add challenge/nonce + signature verification (SIWE/EIP-4361 for EVM, equivalent for Solana).
  - Only set wallet-linked/verified state after successful signature validation.
  - Store chain, address, nonce, signed message hash, verification timestamp.

#### S64-005: Claim endpoint is race-prone; duplicate claim effects are possible under concurrency
- Severity: High
- Location:
  - `app/engine/reward_engine.py:973`
  - `app/engine/reward_engine.py:991`
  - `app/engine/reward_engine.py:1001`
  - `app/models/token_claim_history.py:29`
- Evidence:
  - Claim row read is not `SELECT ... FOR UPDATE`.
  - Duplicate prevention is application-side only (`tokens_claimed > 0` check).
  - No unique constraint enforcing one claim-history entry per `player_id + month_index`.
- Impact: Concurrent requests may both pass pre-checks and duplicate claim accounting/audit entries.
- Fix:
  - Lock allowance row (`with_for_update`) during claim mutation.
  - Add DB uniqueness guard on claim event identity (for example `player_id, month_index` or `claim_intent_id`).
  - Add idempotency key support for claim requests.

#### S64-006: Web bridge allows SSRF via untrusted backend URL override
- Severity: High
- Location:
  - `PFT/pft-expo/web-bridge/app/game/page.tsx:36`
  - `PFT/pft-expo/web-bridge/lib/config.ts:22`
  - `PFT/pft-expo/web-bridge/lib/bridgeApi.ts:1`
  - `PFT/pft-expo/web-bridge/lib/bridgeApi.ts:38`
- Evidence:
  - `backend` query param is accepted and passed through.
  - URL normalization permits arbitrary `http/https` hosts.
  - `server-only` module fetches that host from server context.
- Impact: Attackers can induce the server to request internal/metadata endpoints.
- Fix:
  - Remove query-param backend override in production.
  - Enforce strict allowlist of backend origins.
  - Block private-network and link-local targets at validation and egress layers.

### Medium

#### S64-007: No visible rate limiting on login, wallet-link, or claim endpoints
- Severity: Medium
- Location:
  - `app/api/auth.py:120`
  - `app/api/rewards.py:196`
  - `app/api/rewards.py:358`
  - `app/main.py:360`
  - `requirements.txt:1`
- Evidence:
  - Endpoints process sensitive actions with no throttle controls.
  - No app-level rate-limiter middleware/dependency is present.
- Impact: Increased brute-force and abuse risk (credential stuffing, claim spam, wallet-link abuse).
- Fix:
  - Apply per-IP + per-user rate limits and cooldowns.
  - Add stricter limits for `/auth/login`, `/rewards/link-wallet`, `/rewards/claim`.

#### S64-008: JWT hardening is minimal (no issuer/audience/jti claims)
- Severity: Medium
- Location:
  - `app/api/auth.py:62`
  - `app/api/auth.py:79`
- Evidence:
  - Token payload includes only `sub` and `exp`.
  - Decode path validates signature/algorithm but not `iss`, `aud`, `jti`.
- Impact: Weaker replay controls and weaker cross-service trust boundaries as architecture grows.
- Fix:
  - Add `iss`, `aud`, `iat`, `nbf`, `jti` and strict validation.
  - Support token revocation/versioning for compromised sessions.

#### S64-009: `.env` in workspace contains high-privilege key material names
- Severity: Medium
- Location:
  - `.env:9`
  - `.env:13`
- Evidence:
  - Keys include `SUPABASE_SERVICE_ROLE_KEY` and `INTERNAL_API_KEY`.
- Impact: If `.env` is ever committed or leaked from deployment artifacts, privileged systems can be compromised.
- Fix:
  - Ensure `.env` is never committed and secrets come from runtime secret manager.
  - Rotate service-role/internal keys if exposure is uncertain.

#### S64-010: Security header posture is not explicitly configured
- Severity: Medium
- Location:
  - `PFT/pft-expo/web-bridge/next.config.ts:4`
  - `app/main.py:360`
- Evidence:
  - No CSP/frame-ancestor/header policy in Next config.
  - No backend middleware for host/header hardening is visible in app setup.
- Impact: Reduced defense-in-depth against clickjacking/XSS/misrouting attacks.
- Fix:
  - Add explicit CSP + baseline security headers at edge or app layer.
  - Add host validation middleware and trusted proxy config.

### Low

#### S64-011: Security-sensitive dependencies are unpinned
- Severity: Low
- Location:
  - `requirements.txt:1`
- Evidence:
  - Package versions are unpinned.
- Impact: Non-deterministic installs and uncertain exposure to known CVEs.
- Fix:
  - Pin minimum secure versions and enforce dependency audit in CI.

---

## Step 64 Gap Assessment

### Part 1: Token Boundary
- Status: Mostly met
- Evidence:
  - Token config keeps direct conversion disabled (`app/core/token_config.py:35`).
  - Gameplay/token role separation is clearly documented.
- Hardening needed:
  - Enforce boundary at API/service level via module guards and tests.

### Part 2: Wallet Connection
- Status: Partial
- Implemented:
  - Wallet storage endpoint exists (`/rewards/link-wallet`).
- Missing for secure-by-default:
  - Signature challenge and nonce replay protection.
  - Verified wallet-session binding.

### Part 3: Reward Tracking
- Status: Implemented off-chain
- Implemented:
  - Allowances, balance tracking, history models, monthly pool logic.
- Hardening needed:
  - Decimal/NUMERIC accounting for precision-safe payout math.
  - Concurrency-safe claim transitions.

### Part 4: Claim System
- Status: Partial
- Implemented:
  - Claim API updates off-chain state and history.
- Missing:
  - Signed claim payload generation for contract execution.
  - Idempotency keys + replay nonce model.

### Part 5: Smart Contract Integration
- Status: Not present in scanned scope
- Note:
  - No contract source/integration path was found in scanned project paths.

### Part 6: Security Controls
- Status: Not sufficient for production payout enablement
- Missing:
  - Replay resistance, signature validation, robust rate limiting, admin authorization.

### Part 7: Minimal UI
- Status: Placeholder only
- Implemented:
  - Connect page and wallet prep card.
- Missing:
  - Verified address display, claimable amount, secure claim call.

### Part 8: Domain/Web Integration
- Status: Partial
- Implemented:
  - Canonical host wiring and `/connect` + `/game` pages.
- Risk:
  - Backend override query parameter introduces SSRF risk in production.

### Part 9: Naming Cleanup
- Status: Mostly clean
- Observed:
  - Clear XGP vs PFT naming split in core config/docs.

### Part 10: Validation
- Status: Incomplete
- Observed:
  - No dedicated rewards/token test suite in `tests/` for one-time claim, replay, or wallet proof flows.

---

## Recommended Secure-by-Default Step 64 Architecture

1. Wallet verification flow:
   - `POST /wallet/challenge` returns short-lived nonce + message template bound to user/session.
   - Client signs message with wallet.
   - `POST /wallet/verify` validates signature, chain, nonce freshness, and single-use nonce.
   - Mark wallet `is_verified=true` only after successful verification.

2. Claim intent flow:
   - `POST /claims/intents` creates idempotent claim intent (`intent_id`, `expires_at`, `nonce`) after backend eligibility checks.
   - Persist immutable claim state machine: `created -> signed -> submitted -> confirmed/failed`.
   - Enforce unique constraints at DB layer for `player_id + month_index + terminal_success`.

3. On-chain execution safety:
   - Contract claim function must consume a unique claim ID and reject replays.
   - Backend signs payloads with dedicated signer key in HSM/KMS.
   - Include chain ID, contract address, amount, wallet, intent ID, and expiry in signed domain.

4. Abuse controls:
   - Rate limit login, wallet challenge/verify, claim intent creation/submission.
   - Add anomaly detection (velocity, repeated failed signatures, repeated nonce reuse).

5. Authorization model:
   - Add role claims (`admin`, `ops`) and protect pool/epoch endpoints.
   - Move internal reward maintenance routes behind internal auth, not player auth.

6. Data integrity:
   - Use `NUMERIC`/`Decimal` for token amounts.
   - Use row locks on claim mutations.
   - Add idempotency keys to all state-changing payout endpoints.

---

## Validation Results

Static validation performed:
- Reviewed wallet, claim, auth, and web-bridge paths with line-level evidence.
- Verified current implementation separates gameplay cash from token accounting.
- Verified missing controls for signature-based wallet proof and replay-safe claim execution.

Automated runtime validation:
- Not executed for Step 64 claim security because dedicated claim/wallet tests are not present in `tests/`.

---

## Immediate Action Plan (Recommended Order)

1. Blocker: remove default JWT secret fallback and fail closed on missing secret.
2. Blocker: lock down `/rewards/epoch/*`, `/rewards/player/*`, and pool lifecycle routes to admin/internal auth.
3. Blocker: implement wallet signature nonce verification before any on-chain claim enablement.
4. Blocker: add DB-atomic claim transition (row lock + unique constraints + idempotency keys).
5. Blocker: disable production backend URL override on web bridge and enforce origin allowlist.
6. Add rate limiting + monitoring for login/wallet/claim endpoints.


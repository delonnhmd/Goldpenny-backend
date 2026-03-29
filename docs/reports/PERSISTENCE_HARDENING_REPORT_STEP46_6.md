# Step 46.6 — Persistence Hardening Report

**Date:** 2025-07-18  
**Scope:** Gold Penny Expo app — `src/lib/api/` (15 files) + `src/lib/apiClient.ts` (new)

---

## Summary

Identified and eliminated ~80 lines of copy-pasted AsyncStorage boilerplate duplicated
across 15 API modules. Centralised all HTTP infrastructure into a single source of truth
(`src/lib/apiClient.ts`) and migrated the un-namespaced `identity:uid` key to the
canonical `goldpenny:identity:uid` with a backward-compatible migration path.

---

## 1. Root Cause

All 15 files under `src/lib/api/` contained identical copy-pasted blocks:

| Function | Purpose |
|---|---|
| `getBaseUrl()` | Read `backend:override` from storage, fall back to `BACKEND` env |
| `getIdentityHeaders()` | Generate or restore `identity:uid`, build `X-UID` / `X-Device-FP` headers |
| `fetchJsonPath<T>()` | Make authenticated JSON GET requests |
| `fetchWithFallback<T>()` *(6 files)* | Try multiple URL paths, return first success |
| `postJsonPath<T>()` *(4 files)* | Make authenticated JSON POST requests |

Total duplication: ~80 lines × 15 files = ~1,200 lines of redundant code.

The `identity:uid` key was written independently by each file with no namespace, making
it impossible to migrate safely or audit writes in a single place.

---

## 2. `src/lib/apiClient.ts` — New Canonical Module

Created `src/lib/apiClient.ts` as the single source of truth for all API HTTP infrastructure.

### Canonical AsyncStorage Key Registry

| Exported Constant | Key | Purpose |
|---|---|---|
| `KEY_BACKEND_OVERRIDE` | `backend:override` | Backend URL override (Settings screen) |
| `KEY_ADMIN_TOKEN` | `admin:token` | Admin bearer token (Settings screen) |
| `KEY_ADMIN_ADDRESS` | `admin:address` | Admin wallet address (Settings screen) |
| `KEY_IDENTITY_UID` | `goldpenny:identity:uid` | Canonical device identity UID |

### Identity Key Migration

`resolveIdentityUid()` implements a one-time migration on first read after an upgrade:

1. Read `goldpenny:identity:uid` → return if present (fast path)
2. Fall back to legacy `identity:uid` (read-only)
3. Promote value to `goldpenny:identity:uid` with `setItem`
4. From this point all reads hit only the canonical key

This is backward-compatible: existing devices silently upgrade on first app load.

### Exported Functions

| Function | Replaces | Notes |
|---|---|---|
| `getBaseUrl()` | `getBaseUrl()` in every file | Validates `https?://` pattern on overrides |
| `getIdentityHeaders()` | `getIdentityHeaders()` in every file | Calls `resolveIdentityUid()` for migration |
| `fetchApi<T>(path, init?)` | All `fetchJsonPath<T>` variants | Supports GET and POST; full error handling |
| `fetchApiWithFallback<T>(paths[], init?)` | All `fetchWithFallback<T>` variants | Accumulates errors across all paths |

---

## 3. Files Refactored (15 total)

All 15 files had identical changes applied:

**Removed:**
- `import AsyncStorage from '@react-native-async-storage/async-storage';`
- `import { BACKEND } from '@/constants';`
- `async function getBaseUrl() {...}`
- `async function getIdentityHeaders() {...}`
- `async function fetchJsonPath<T>() {...}`

**Removed (where present):**
- `async function fetchWithFallback<T>() {...}` — 6 files
- `async function postJsonPath<T>() {...}` — 4 files

**Added:**
- `import { fetchApi } from '@/lib/apiClient';` — 9 files (GET/POST only)
- `import { fetchApiWithFallback } from '@/lib/apiClient';` — 6 files (fallback pattern)

### File-by-file summary

| File | Imported | Special handling |
|---|---|---|
| `commitment.ts` | `fetchApiWithFallback` | — |
| `consumerBorrowing.ts` | `fetchApi` | `postJsonPath(path, body)` → `fetchApi(path, { method:'POST', body: JSON.stringify(body) })` |
| `contractTiming.ts` | `fetchApi` | `postJsonPath(path)` → `fetchApi(path, { method:'POST' })` (×2) |
| `economyPresentation.ts` | `fetchApiWithFallback` | — |
| `financialSurvival.ts` | `fetchApi` | — |
| `forecasting.ts` | `fetchApi` | `postJsonPath(path, body)` → `fetchApi(path, { method:'POST', body: JSON.stringify(body) })` (×3) |
| `gameplay.ts` | `fetchApiWithFallback` | — |
| `onboarding.ts` | `fetchApiWithFallback` | Non-contiguous boilerplate (helpers between getIdentityHeaders and fetchJsonPath) |
| `personalShocks.ts` | `fetchApi` | — |
| `populationPressure.ts` | `fetchApi` | `fetchJsonPath(path, 'POST')` → `fetchApi(path, { method:'POST' })` |
| `progression.ts` | `fetchApiWithFallback` | — |
| `strategicPlanning.ts` | `fetchApiWithFallback` | — |
| `supplyChain.ts` | `fetchApi` | `postJsonPath(path)` → `fetchApi(path, { method:'POST' })` |
| `wealthProgression.ts` | `fetchApi` | — |
| `worldMemory.ts` | `fetchApi` | `fetchJsonPath(path, 'POST')` → `fetchApi(path, { method:'POST' })` |

---

## 4. Gameplay-Layer Persistence Audit

A full audit of all remaining AsyncStorage usage outside `src/lib/api/` was performed.
Four locations were identified: `apiClient.ts` (canonical), `useDailyProgression.ts`,
`app/gameplay/index.tsx`, and `app/(tabs)/settings.tsx`.

### 4a. `src/hooks/useDailyProgression.ts` — No changes needed

| Check | Result |
|---|---|
| Key naming | ✅ Player-scoped namespaced keys: `goldpenny:gameplay:day:${playerId}`, `goldpenny:gameplay:lastProcessedDay:${playerId}` |
| Double-load guard | ✅ `initialized.current` ref prevents redundant reads on re-mount |
| Hydration safety | ✅ `Promise.all` parallel load; `parseInt` + `isFinite` + `>= DEFAULT_START_DAY` validation; safe defaults on all parse failures |
| Write timing | ✅ `markDayAdvanced()` uses `isAdvancingDay` flag to prevent concurrent writes; `markDayStarted()` uses intentional fire-and-forget `.catch(() => {})` |
| Failure tolerance | ✅ Full `try/catch` on load; silently degrades to defaults on error |
| Naming integrity | ✅ No NNT/GNNT/nnt-token references |

### 4b. `app/gameplay/index.tsx` — No changes needed

| Check | Result |
|---|---|
| Key naming | ✅ `PLAYER_ID_STORAGE_KEY = 'goldpenny:gameplay:lastPlayerId'` (canonical, namespaced, local constant) |
| Legacy migration | ✅ `LEGACY_PLAYER_ID_STORAGE_KEY = 'gameplay:lastPlayerId'` — read-only fallback on load; new writes always go to canonical key |
| Hydration safety | ✅ `try/catch` on read; falls back to empty string on failure; validation (`trim()`) before use |
| Write safety | ✅ `try/catch` on write; write failure is non-fatal (persistence marked optional in comment) |
| Naming integrity | ✅ No NNT/GNNT/nnt-token references |

### 4c. `app/(tabs)/settings.tsx` — Constants import added

**Issue found:** All three admin/backend key strings were hardcoded inline as string literals
(`'backend:override'`, `'admin:token'`, `'admin:address'`) across 11 call sites, including
the `multiRemove` array. These exact strings are already exported as constants from
`apiClient.ts` (`KEY_BACKEND_OVERRIDE`, `KEY_ADMIN_TOKEN`, `KEY_ADMIN_ADDRESS`).

Using string literals creates a silent drift risk: a key renamed in `apiClient.ts` (the
reader) while the literal persists in `settings.tsx` (the writer) would result in
`apiClient.ts` always reading `null` with no error.

**Fix applied:** Added import of `KEY_BACKEND_OVERRIDE`, `KEY_ADMIN_TOKEN`,
`KEY_ADMIN_ADDRESS` from `@/lib/apiClient` and replaced all 11 occurrences of inline
string literals with the constants. Other logic in `settings.tsx` unchanged.

---

## 5. No-Change Files

| File | Reason |
|---|---|
| `src/hooks/useDailySession.ts` | Pure in-memory state; no AsyncStorage usage |

---

## 6. Complete Canonical AsyncStorage Key Registry

All active keys written by this app, with their authoritative owner:

| Key | Constant | Owner | Migrated From |
|---|---|---|---|
| `goldpenny:identity:uid` | `KEY_IDENTITY_UID` | `apiClient.ts` | `identity:uid` |
| `goldpenny:gameplay:lastPlayerId` | local `PLAYER_ID_STORAGE_KEY` | `app/gameplay/index.tsx` | `gameplay:lastPlayerId` |
| `goldpenny:gameplay:day:${playerId}` | — | `useDailyProgression.ts` | — |
| `goldpenny:gameplay:lastProcessedDay:${playerId}` | — | `useDailyProgression.ts` | — |
| `backend:override` | `KEY_BACKEND_OVERRIDE` | `apiClient.ts` + `settings.tsx` | — |
| `admin:token` | `KEY_ADMIN_TOKEN` | `settings.tsx` | — |
| `admin:address` | `KEY_ADMIN_ADDRESS` | `settings.tsx` | — |

Legacy keys `identity:uid` and `gameplay:lastPlayerId` are read-only during migration;
no new writes ever target them.

---

## 7. Known Gap (out of scope)

`src/hooks/useBackend.ts` maintains its own in-memory `backendOverride` variable
(defaulting to `null` on cold start) and exposes `setBackendOverride()` which is never
called from `settings.tsx`. As a result, `useBackend`-based calls (used by `useDebt` and
`useRegistration` — wallet auth, debt context) do not pick up the saved override across
restarts.

This is a pre-existing issue noted in Steps 45.8, 46.1, and 46.2 reports and remains out
of scope for gameplay-layer hardening. All `src/lib/api/` modules that drive the active
gameplay loop use `apiClient.ts`, which reads from AsyncStorage on every request.

---

## 8. Identity Key Migration Details

**Before:** Every API file independently wrote `identity:uid` (no namespace, no central authority).  
**After:** `apiClient.ts` is the only writer. Key promoted from `identity:uid` → `goldpenny:identity:uid` on first read after upgrade.

```
Old devices:  identity:uid   →  read once  →  write goldpenny:identity:uid  →  done
New devices:                                    write goldpenny:identity:uid  →  done
```

Migration is silent, idempotent, and runs at most once per device.

---

## 9. Validation

| Check | Result |
|---|---|
| `npx tsc --noEmit` | ✅ 0 errors |
| `npx expo lint` | ✅ 0 errors / 12 warnings (all pre-existing) |
| Naming integrity (NNT/GNNT/nnt-token) | ✅ No leakage found in any touched file |

Pre-existing warnings unchanged:
- `progression.ts`: `StreakItem`, `WeeklyMissionItem` unused type imports
- `consumerBorrowing.ts`, `financialSurvival.ts`: `Array<T>` type style (×4)

---

## 10. Architecture After Refactor

```
src/lib/
  apiClient.ts          ← single source of truth for all HTTP + persistence
  api/
    commitment.ts       ← imports fetchApiWithFallback
    consumerBorrowing.ts← imports fetchApi
    contractTiming.ts   ← imports fetchApi
    economyPresentation.ts← imports fetchApiWithFallback
    financialSurvival.ts← imports fetchApi
    forecasting.ts      ← imports fetchApi
    gameplay.ts         ← imports fetchApiWithFallback
    onboarding.ts       ← imports fetchApiWithFallback
    personalShocks.ts   ← imports fetchApi
    populationPressure.ts← imports fetchApi
    progression.ts      ← imports fetchApiWithFallback
    strategicPlanning.ts← imports fetchApiWithFallback
    supplyChain.ts      ← imports fetchApi
    wealthProgression.ts← imports fetchApi
    worldMemory.ts      ← imports fetchApi
```


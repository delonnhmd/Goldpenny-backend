# Domain Standardization Report — Step 46.4.1

**Date:** 2025-10-04  
**Scope:** Full repository domain audit and canonicalization  
**Baseline:** Step 46.4 complete (0 TS errors, 12 ESLint warnings)

---

## Canonical Domain Rules Established

| Purpose | Canonical URL |
|---|---|
| Main website / platform identity | `https://www.pennyfloat.com` |
| Gold Penny game + wallet/web3 bridge | `https://goldpenny.pennyfloat.com` |
| **Forbidden** | `goldpenny.app`, `nntpress.com` |

---

## Full Repository Scan Results

Scanned all `.ts`, `.tsx`, `.py`, `.json`, `.md`, `.env` files (excluding `node_modules`, `__pycache__`, `.expo`, `.venv`).

Pattern: `goldpenny\.app|nntpress\.com|pennyfloat`

### Active Runtime Files

| File | Line | Old Value | New Value | Action |
|---|---|---|---|---|
| `src/constants/index.ts` | 13 | `'https://goldpenny.app'` | `'https://goldpenny.pennyfloat.com'` | ✅ **FIXED** |

### Backend

| File | Finding | Action |
|---|---|---|
| `goldpenny-backend/.env` | No domain URLs — only DB connection string + Supabase URL | No change needed |
| `goldpenny-backend/app/main.py` | No CORS middleware / no hardcoded origins | No change needed |
| `goldpenny-backend/app/core/__init__.py` | Line 1: brand comment `Gold Penny / PennyFloat.` — no URL | No change needed |

### Historical Step-Report Markdown (Not Updated — Accurate Archive)

These files contain legacy domain strings documenting **past values at the time the step was executed**. They are accurate historical records, not active runtime references.

| File | Legacy Domain Mentioned | Context |
|---|---|---|
| `CLEANUP_REPORT_STEP43_5.md:195` | `nntpress.com` | Historical Android package value in audit table |
| `APP_STARTUP_SMOKETEST_REPORT_STEP45_8.md:98` | `nntpress.com` | Historical `android.package` value (preserved at that step) |
| `PATH_REFACTOR_AND_DAILY_PROGRESSION_REPORT_STEP46_3.md:42,53,67` | `nntpress.com`, `goldpenny.app` | Before/after table showing rename history |
| `MOBILE_IDENTITY_AND_JOB_INCOME_REPORT_STEP46_4.md:51,59,61` | `goldpenny.app`, `nntpress.com` | Pre-fix state documented in Step 46.4 report |
| `REFERENCE_SWEEP_REPORT_STEP45_7.md:117` | `nntpress.com` | Historical identity preservation table |
| `RENAME_ALIGNMENT_REPORT.md:64` | `nntpress.com` | Rename history documentation |

---

## Fix Applied

**File:** `src/constants/index.ts`  

```diff
 export const WC_METADATA = {
   name: 'Gold Penny',
   description: 'Gold Penny mobile client',
-  url: 'https://goldpenny.app',
+  url: 'https://goldpenny.pennyfloat.com',
   icons: ['https://walletconnect.com/_next/static/media/walletconnect-logo.9c2a3e16.svg'],
 };
```

---

## Validation

| Check | Result |
|---|---|
| `npx tsc --noEmit` | ✅ 0 errors |
| `npx expo lint` | ✅ 0 errors, 12 pre-existing warnings (unchanged) |
| New regressions | None |

---

## Summary

- **1 active runtime file updated** — `WC_METADATA.url` in `src/constants/index.ts`
- **No backend CORS middleware exists** — no hardcoded origins to update
- **No domain URLs in `.env`** — Supabase URL already uses correct Supabase infrastructure
- **6 historical step-report markdown files** reference legacy domains as historical records — left unchanged (they document accurate past state)
- All active runtime code now exclusively uses `goldpenny.pennyfloat.com` for the game/wallet web3 domain

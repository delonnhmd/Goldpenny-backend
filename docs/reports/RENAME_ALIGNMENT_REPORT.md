# Rename Alignment Report

**Date:** 2026-03-21  
**Renames applied:**
- `nnt-expo` → `pft-expo`
- `NNT-token` → `UI` → `PFT` (second rename applied after Step 45.6)

---

## Files Updated

### 1. `app.json`
| Field | Before | After |
|---|---|---|
| `expo.slug` | `"nnt-expo"` | `"pft-expo"` |

> **Note:** The EAS project slug controls OTA update delivery URLs. After this change, a full EAS re-build is required to re-register the project slug. The update URL (`expo.updates.url`) and project ID remain unchanged.

---

### 2. `android/settings.gradle`
| Field | Before | After |
|---|---|---|
| `rootProject.name` | `'nnt-expo'` | `'pft-expo'` |

---

### 3. `android/app/src/main/res/values/strings.xml`
| Field | Before | After |
|---|---|---|
| `app_name` string resource | `nnt-expo` | `pft-expo` |

---

### 4. `android/app/src/main/AndroidManifest.xml`
| Field | Before | After |
|---|---|---|
| Expo dev scheme | `exp+nnt-expo` | `exp+pft-expo` |
| Slug-derived scheme | `nntexpo` | `pftexpo` |

---

### 5. `app/_layout.tsx`
| Field | Before | After |
|---|---|---|
| File path comment (line 1) | `// nnt-expo/app/_layout.tsx` | `// pft-expo/app/_layout.tsx` |

---

### 6. `FINAL_WIPE_UNUSED_REPORT_STEP45_6.md`
| Field | Before | After |
|---|---|---|
| Project root reference | `` `nnt-token/nnt-expo` `` | `` `PFT/pft-expo` `` |

---

## Ambiguous Cases — Skipped

| Location | Value | Reason skipped |
|---|---|---|
| `app.json → expo.scheme` | `"nnt"` | Deep-link URI scheme used for WalletConnect wallet auth callbacks. Renaming would break all existing `nnt://` deep links and wallet connectors in the wild. |
| `AndroidManifest.xml` (data-generated intent filter) | `android:scheme="nnt"` and `android:host="nnt.example"` | Auto-generated from `expo.scheme = "nnt"`. Tied to the deep-link infrastructure above. |
| `AndroidManifest.xml` | `android:scheme="nnt"` (intentFilters) | Same reason — app.json scheme. |
| `app.json → android.package` | `"nntpress.com"` | Reverse-domain Android package identifier. Changing this invalidates the published app identity and breaks Play Store distribution. |
| `src/constants/index.ts` comment | `// NNT/GNNT token addresses` | References to archived token names in a comment documenting removed code. Accurate historical note, not a branding string. |
| `app/(tabs)/index.tsx` comment | `archive/nnt-legacy/nnt-expo-nnt-only/...` | References the archive directory path. Archive content is intentionally preserved as-is. |
| `goldpenny-backend/CLEANUP_REPORT_STEP43_5.md` | Multiple `nnt-expo`, `nnt-token` refs | Historical cleanup report — records of past work, not active code. |
| `archive/nnt-legacy/...` (all files) | All `nnt-token`, `nnt-expo` refs | Legacy archive — intentionally preserved as historical record. |
| `android/build/` (generated files) | All `nnt-token/nnt-expo` path refs | Build artifacts (`autolinking.json`, `problems-report.html`, ESLint cache). Will be auto-regenerated on next build. |
| `.expo/cache/eslint/.cache_z6nzu4` | Absolute path strings | ESLint cache file — auto-regenerated. |

---

## No-Op Checks (no matches found)

- `tsconfig.json` path aliases — no `nnt-expo` or `NNT-token` references  
- `package.json` name — already `"goldpenny-expo"` (updated in prior Step 43.5)  
- `metro.config.js` — no `nnt` references  
- `babel.config.js` — no `nnt` references  
- `eas.json` — no `nnt` references  
- `.env` / `.env` (nnt-token root) — no branding strings (only contract addresses and RPC URLs)  
- `src/` source files — no `nnt-expo` or `NNT-token` strings  
- Backend Python app (`goldpenny-backend/app/`) — no `nnt-expo` or `NNT-token` references  
- `README.md` — no `nnt` branding references  

---

## Summary

| Category | Count |
|---|---|
| Files updated | 6 |
| References replaced | 8 |
| Ambiguous / skipped | 11 (documented above) |
| Build artifacts (regenerate on rebuild) | 3 |

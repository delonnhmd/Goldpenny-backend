# Reference Sweep Report — Step 45.7

> Full repository integrity sweep executed after Step 45.6 rename alignment (nnt-expo → pft-expo).
> Scope: `app/`, `src/`, `src/pages/`, config files, tsconfig, build config.
> Excludes: `archive/`, `unused/`, `.expo/cache/` (build artifacts / quarantine zones).

---

## 1. App Route Integrity

| Route File | Status | Notes |
|---|---|---|
| `app/_layout.tsx` | ✅ Clean | Root layout — `WalletProvider`, `DebtProvider`, `Stack`. File comment updated to `pft-expo/`. |
| `app/(tabs)/_layout.tsx` | ✅ Clean | 2 tabs: `index` (Gold Penny) + `settings`. Imports `TopStatusBar`, `HapticTab`, `IconSymbol`, `Colors`, `useColorScheme` — all resolve. |
| `app/(tabs)/index.tsx` | ✅ Clean | Redirects to `/gameplay`. One informational comment referencing archive path — functionally inert. |
| `app/(tabs)/settings.tsx` | ✅ Clean | Backend URL override, admin token, auto-update toggle. Uses `AsyncStorage`, `expo-updates`. No broken imports. |
| `app/gameplay/index.tsx` | ✅ Clean | Player ID entry; reads `AsyncStorage` key `gameplay:lastPlayerId`. All `@/components/layout/` and `@/components/ui/` imports resolve. |
| `app/gameplay/[playerId].tsx` | ✅ Clean | Unwraps `playerId` from router params; delegates to `@/pages/gameplay/GameDashboardPage`. Single import, resolves correctly. |
| `app/account/` | ✅ Empty stub | Directory exists, no files — expected placeholder. |
| `app/admin/` | ✅ Empty stub | Directory exists, no files — expected placeholder. |
| `app/claim/` | ✅ Empty stub | Directory exists, no files — expected placeholder. |
| `app/leaderboard/` | ✅ Empty stub | Directory exists, no files — expected placeholder. |
| `app/post/` | ✅ Empty stub | Directory exists, no files — expected placeholder. |
| `app/referral/` | ✅ Empty stub | Directory exists, no files — expected placeholder. |
| `app/user/` | ✅ Empty stub | Directory exists, no files — expected placeholder. |

---

## 2. Pages Layer

| File | Status | Notes |
|---|---|---|
| `src/pages/gameplay/GameDashboardPage.tsx` | ✅ Clean | Imports 52 gameplay components, 8 lib/api modules, 10 types modules, 3 lib utilities, 2 hooks. All resolve against confirmed directory contents. |

---

## 3. Components Layer

### `src/components/gameplay/` (52 files)
All files imported by `GameDashboardPage.tsx` verified against directory listing. ✅ No missing files, no stale references.

### `src/components/layout/` (9 files)
`AppShell`, `BottomActionBar`, `BottomNav`, `ContentStack`, `MobileTabShell`, `PageContainer`, `ResponsiveGrid`, `SafeAreaPage`, `TopBar` — all present.

### `src/components/ui/` (18 files)
`ActionRow`, `Badge`, `Divider`, `EmptyStateView`, `ErrorStateView`, `icon-symbol.android/ios/.tsx`, `IconLabelRow`, `InlineStat`, `LoadingSkeleton`, `PrimaryButton`, `ProgressMeter`, `SecondaryButton`, `SectionCard`, `StatusChip`, `SurfaceCard`, `TextButton` — all present.

### `src/components/motion/` (3 files)
`ExpandCollapseView`, `FadeInView`, `SlideUpPanel` — all present.

### `src/components/TopStatusBar.tsx`
✅ Clean — only imports `useDebt`. All NNT/GNNT balance display removed in Step 43.5. Shows debt warning only.

### `src/components/haptic-tab.tsx`
✅ Present — resolves via `@/components/haptic-tab` alias.

### Barrel index files
No `index.ts` / `index.tsx` barrel files exist under `src/components/`. All imports are direct module paths — no stale barrel exports possible.

---

## 4. Hooks Layer

| File | Status | Notes |
|---|---|---|
| `src/hooks/index.tsx` | ✅ Clean | Exports: `useBackend`, `useRegistration`, `useWallet`, `useDebt`. Archived NNT-only hooks noted in comment. |
| `src/hooks/useDebt.tsx` | ✅ Clean | Imports `useWallet`, `useBackend` — both resolve. |
| `src/hooks/useWallet.tsx` | ✅ Present | Active wallet hook (not the `unused/hooks/useWallet.ts` old version). |
| `src/hooks/useBackend.ts` | ✅ Present | |
| `src/hooks/useRegistration.ts` | ✅ Present | |
| `src/hooks/useDailySession.ts` | ✅ Present | Exports `ActionExecutionGuard` + `useDailySession`, imported by `GameDashboardPage`. |
| `src/hooks/useBreakpoint.ts` | ✅ Present | Imported by `GameDashboardPage`. |
| `src/hooks/use-color-scheme.ts` | ✅ Present | Imported by `(tabs)/_layout.tsx`. |

---

## 5. Constants & Design Layer

| File | Status | Notes |
|---|---|---|
| `src/constants/index.ts` | ✅ Clean | Exports: `BACKEND`, `BUILD_TS`, `CHAIN_ID`, `RPC_URL`, `WC_PROJECT_ID`, `WC_METADATA`. Comment about archived NNT_ADDRESS/GNNT_ADDRESS is informational only. |
| `src/constants/theme.ts` | ✅ Clean | Exports `Colors`, `Fonts`. Imported by `(tabs)/_layout.tsx` as `@/constants/theme`. |
| `src/design/theme.ts` | ✅ Present | Exports `{ theme }`. Used by `gameplay/index.tsx` and `GameDashboardPage.tsx`. |
| `src/design/breakpoints.ts` | ✅ Present | Supporting design tokens. |
| `src/design/motion.ts` | ✅ Present | Supporting animation tokens. |
| `src/design/tokens.ts` | ✅ Present | Supporting design tokens. |

No `src/constants/contracts.ts` exists (was removed in a prior cleanup step — confirmed absent, no imports reference it).

---

## 6. Lib Layer

### `src/lib/api/` (15 files)
`commitment`, `consumerBorrowing`, `contractTiming`, `economyPresentation`, `financialSurvival`, `forecasting`, `gameplay`, `onboarding`, `personalShocks`, `populationPressure`, `progression`, `strategicPlanning`, `supplyChain`, `wealthProgression`, `worldMemory`

All modules imported by `GameDashboardPage.tsx` verified ✅: `commitment`, `economyPresentation`, `gameplay`, `progression`, `onboarding`, `strategicPlanning`, `worldMemory`.

### `src/lib/` (formatter/util files)
`commitmentFormatters`, `economyPresentationFormatters`, `gameplayFormatters`, `logger`, `onboardingFormatters`, `populationPressureFormatters`, `strategicPlanningFormatters`, `uiSummaryFormatters`, `ui_layout_config`, `worldMemoryFormatters` — all present. `uiSummaryFormatters` and `ui_layout_config` verified as imported by `GameDashboardPage.tsx` ✅.

---

## 7. Types Layer

### `src/types/` (15 files)
`commitment`, `consumerBorrowing`, `contractTiming`, `economyPresentation`, `financialSurvival`, `forecasting`, `gameplay`, `onboarding`, `personalShocks`, `populationPressure`, `progression`, `strategicPlanning`, `supplyChain`, `wealthProgression`, `worldMemory`

All type imports in `GameDashboardPage.tsx` verified ✅.

---

## 8. Config Files

| File | Status | Notes |
|---|---|---|
| `app.json` | ✅ Updated | `slug: "pft-expo"` (changed Step 45.6). `scheme: "nnt"` kept (WalletConnect). `android.package: "nntpress.com"` kept (published identity). |
| `tsconfig.json` | ✅ Clean | `paths: { "@/*": ["src/*", "./*"] }`. `exclude: ["node_modules", "unused"]` — confirms `unused/` is excluded from compilation. |
| `babel.config.js` | ✅ Clean | `module-resolver` alias `@` → `./src`. `react-native-reanimated/plugin` last (correct). |
| `metro.config.js` | ✅ Clean | `@reown/appkit*` shimmed to empty stubs. No old naming references. |
| `eas.json` | ✅ Clean | Three profiles: `development`, `preview`, `production`. All `internal` distribution. No `nnt-expo` references. |
| `android/settings.gradle` | ✅ Updated | `rootProject.name = 'pft-expo'` (changed Step 45.6). |
| `android/.../strings.xml` | ✅ Updated | `app_name = pft-expo` (changed Step 45.6). |
| `android/AndroidManifest.xml` | ✅ Updated | Schemes `exp+pft-expo`, `pftexpo`. `scheme="nnt"` kept. (changed Step 45.6). |

---

## 9. Naming Leftover Scan — `src/` + `app/`

Searched patterns: `nnt-expo`, `NNT-token`, `nnt-token`, `NNT token`, `nnt token`

| Location | Match | Category | Action |
|---|---|---|---|
| `app/(tabs)/index.tsx` line 4 | `// (Legacy NNT post-feed home is archived at archive/nnt-legacy/nnt-expo-nnt-only/...)` | Informational comment — archive path | No action — intentionally documents history |
| `src/constants/index.ts` line 17 | `// ─── ARCHIVED (NNT/GNNT token addresses — see archive/nnt-legacy/) ────────────` | Informational comment — cleanup note | No action — intentionally documents removed exports |
| `.expo/cache/eslint/.cache_ufaeuf` | Old `C:\Users\mdnoi\nnt-token\nnt-expo\...` paths throughout | ESLint build artifact | No action — auto-regenerated on next `expo start` |

**Result: 0 functional naming issues in source code.**

---

## 10. Quarantine Zone Verification

`unused/` directory is excluded from TypeScript compilation (`tsconfig.json exclude`). Confirmed by searching all active `src/` and `app/` files: zero imports reference any path under `unused/`.

Contents of `unused/` remain:
- `unused/hooks/useWallet.ts` — archived old wallet hook
- `unused/components/` — 9 archived components (AdminPanel, collapsible, external-link, hello-wave, parallax-scroll-view, PostModerator, themed-text, themed-view, UserModerator)
- `unused/screens/` — authors.tsx, modal.tsx, settings.tsx
- `unused/legacy/`, `unused/design-specs/`, `unused/utils/`

---

## 11. Summary

| Category | Issues Found | Issues Fixed | Status |
|---|---|---|---|
| Broken imports | 0 | 0 | ✅ Clean |
| Stale barrel exports | 0 | 0 | ✅ None exist |
| Old naming in functional code | 0 | 0 | ✅ Clean |
| Comments with old naming | 2 | 0 | ✅ Informational only — no action needed |
| Build artifact cache | 1 file | 0 | ✅ Auto-regenerates |
| Config consistency | All aligned | — | ✅ Verified |
| Router integrity | 2 active routes | — | ✅ Verified |
| Empty stub directories | 7 | — | ✅ Expected placeholders |

**Overall status: PASSED. No broken references, no stale exports, no functional naming leftovers. App is structurally sound.**

---

*Generated: Step 45.7 — Post-rename integrity sweep*
*Scope: goldpenny-backend/nnt-token/nnt-expo (active app)*

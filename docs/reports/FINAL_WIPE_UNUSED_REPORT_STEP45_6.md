# Step 45.6 — Final Wipe: Unused Files Report

**Date:** 2025-10-04  
**Project root:** `PFT/pft-expo`  
**Prior cleanup:** Step 43.5 (Legacy NNT archival to `archive/nnt-legacy/`)  

---

## Summary

19 files confirmed unused and moved to `unused/`. TypeScript compile: **0 errors**.

---

## Files Moved

### `unused/screens/` — Dead App Routes (Expo Router)

| Original path | Reason unused |
|---|---|
| `app/authors.tsx` | NNT social screen — no navigation links from any active route |
| `app/modal.tsx` | Expo boilerplate modal — no `router.push('/modal')` calls anywhere |
| `app/settings.tsx` | Root-level duplicate of `app/(tabs)/settings.tsx` — unreachable via tab nav |

### `unused/components/` — Unreferenced UI Components

| Original path | Reason unused |
|---|---|
| `src/components/hello-wave.tsx` | Expo starter boilerplate — zero imports |
| `src/components/external-link.tsx` | Expo starter boilerplate — zero imports |
| `src/components/parallax-scroll-view.tsx` | Only referenced by `app/modal.tsx` (also moved) |
| `src/components/themed-text.tsx` | Only referenced by `app/modal.tsx` and `ui/collapsible.tsx` (both moved) |
| `src/components/themed-view.tsx` | Only referenced by `app/modal.tsx` and `parallax-scroll-view.tsx` (both moved) |
| `src/components/ui/collapsible.tsx` | Expo boilerplate — only referenced by `app/modal.tsx` (moved); NOT the same as `src/components/gameplay/CollapsibleSection.tsx` (active) |
| `src/components/admin/AdminPanel.tsx` | NNT admin panel — zero imports (NNT routes archived in Step 43.5) |
| `src/components/admin/PostModerator.tsx` | NNT admin component — zero imports |
| `src/components/admin/UserModerator.tsx` | NNT admin component — zero imports |

### `unused/design-specs/` — Figma & Design Spec Files

| Original path | Reason unused |
|---|---|
| `src/design/figmaMapping.ts` | Design spec only — zero runtime imports; imports componentSpec/screenSpec (also dead chain) |
| `src/design/componentSpec.ts` | Only imported by `figmaMapping.ts` (also moved) |
| `src/design/screenSpec.ts` | Only imported by `figmaMapping.ts` (also moved) |
| `src/design/launchUiChecklist.ts` | Launch checklist data — zero runtime imports |

### `unused/legacy/` — Old NNT Constants

| Original path | Reason unused |
|---|---|
| `src/constants/contracts.ts` | NNT/GNNT contract addresses — zero imports in Gold Penny codebase |

### `unused/hooks/` — Dead Hook Files

| Original path | Reason unused |
|---|---|
| `src/hooks/useWallet.ts` | 1-line re-export shim (`export * from './wallet-context'`) — shadowed/replaced by `useWallet.tsx` (340-line full implementation) |

### `unused/utils/` — Dead Utility Files

| Original path | Reason unused |
|---|---|
| `src/utils/format.ts` | Zero imports across entire project |

---

## Files Confirmed Active (NOT Moved)

### Motion Components — All Active
- `src/components/motion/ExpandCollapseView.tsx` — used by `CollapsibleSection.tsx`
- `src/components/motion/FadeInView.tsx` — used by `GameDashboardPage.tsx`
- `src/components/motion/SlideUpPanel.tsx` — used by `ActionPreviewModal.tsx`

### Design System — All Active
- `src/design/theme.ts` — imported by `src/constants/theme.ts`
- `src/design/tokens.ts` — imported by `src/design/theme.ts`
- `src/design/breakpoints.ts` — imported by `src/hooks/useBreakpoint.ts`
- `src/design/motion.ts` — imported by all three motion components

### Hooks — All Active
- `src/hooks/useWallet.tsx` — `WalletProvider` used by `app/_layout.tsx`
- `src/hooks/wallet-context.tsx` — re-exported by `useWallet.tsx`
- `src/hooks/useDebt.tsx` — `DebtProvider` used by `app/_layout.tsx`
- `src/hooks/useBackend.ts` — core Gold Penny HTTP layer
- `src/hooks/useRegistration.ts` — Gold Penny auth flow
- `src/hooks/useBreakpoint.ts` — used by `GameDashboardPage.tsx` and `SlideUpPanel.tsx`
- `src/hooks/useResponsiveValue.ts` — used by `ResponsiveGrid.tsx`
- `src/hooks/useDailySession.ts` — used by `GameDashboardPage`, `ActionCard`, `ActionHubPanel`, `ActionPreviewModal`

### Infrastructure — All Active
- `src/shims/async-require.ts` — metro.config.js alias for `@expo/metro-config/build/async-require.js`
- `src/shims/empty.ts` — metro.config.js alias for `@reown/appkit*` packages
- `src/lib/ui_layout_config.ts` — used by `GameDashboardPage.tsx`
- `src/pages/gameplay/GameDashboardPage.tsx` — used by `app/gameplay/[playerId].tsx`

---

## Config Change

**`tsconfig.json`** — added `unused` to `exclude` list to prevent TypeScript from type-checking quarantined files:

```json
"exclude": ["node_modules", "unused"]
```

---

## Validation Results

| Check | Result |
|---|---|
| `npx tsc --noEmit` | ✅ 0 errors |
| Active routes intact | ✅ `(tabs)/index`, `(tabs)/settings`, `gameplay/index`, `gameplay/[playerId]` all present |
| Providers intact | ✅ `WalletProvider` + `DebtProvider` in `app/_layout.tsx` |
| Motion components | ✅ All 3 active (`ExpandCollapseView`, `FadeInView`, `SlideUpPanel`) |
| Admin folder | ✅ `src/components/admin/` is now empty (all 3 files moved) |

---

## Reference Audit Methodology

Each file was checked with `grep_search` across all `**/*.{ts,tsx}` files to find import references. Files where the only matches were within the file itself (self-declarations), or only within other dead files, were classified as unused.

Special checks:
- `collapsible.tsx` — distinguished from `gameplay/CollapsibleSection.tsx` (which is active)
- `useWallet.ts` vs `useWallet.tsx` — `.tsx` takes precedence in TS resolution; `.ts` was a legacy shim
- `app/settings.tsx` (root) vs `app/(tabs)/settings.tsx` — root version is unreachable via tab navigation and has no inbound `router.push` calls
- `design/tokens.ts`, `design/theme.ts`, `design/breakpoints.ts`, `design/motion.ts` — all confirmed ACTIVE (part of live design system chain used by gameplay components)

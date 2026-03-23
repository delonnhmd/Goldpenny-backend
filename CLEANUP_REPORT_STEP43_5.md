# Step 43.5 — Legacy NNT Separation Cleanup Report

**Date:** 2026-03-21  
**TypeScript compile after cleanup:** ✅ Zero errors (`npx tsc --noEmit`)

---

## Overview

This report documents the separation of the legacy NNT/GNNT blockchain token
infrastructure from the active Gold Penny / PFT game code.

All archived files are preserved under `archive/nnt-legacy/` — nothing has been
permanently deleted (except two confirmed-empty stub files).

---

## 1. Archived — `nnt-token/` Root Level

**Location:** `archive/nnt-legacy/nnt-token-root/`

### Files archived
| File | Reason |
|---|---|
| `backend.py` | Legacy Flask NNT backend |
| `requirements.txt` | Python deps for legacy Flask backend |
| `hardhat.config.js` | Hardhat blockchain toolchain config |
| `flattened.sol` | Flattened Solidity for NNT contracts |
| `encode.js` | NNT encoding utility |
| `printenv.js` | Legacy debug script |
| `ad_pool_state.json` | NNT ad pool runtime state |
| `airdrop-gnnt-epoch200.json` | GNNT epoch 200 airdrop data |
| `airdrop-nnt-epoch100.json` | NNT epoch 100 airdrop data |
| `points_db.json` | Legacy NNT points database |
| `posts.json` / `posts_db.json` | Legacy NNT posts data |
| `package.json` / `package-lock.json` | Hardhat npm package (NOT the Expo one) |
| `FIXES_APPLIED.md` / `STABILITY_FIXES.md` / `README.md` | Legacy NNT docs |
| `test_backend.py` / `test_backend_startup.py` / `test_flask.py` / `test_stability.py` | Legacy NNT Python tests |
| `test-backend.ps1` | Legacy NNT PowerShell test |
| `Website sketch.png` / `Create an image of a.png` | Misc design assets |

### Directories archived
| Directory | Reason |
|---|---|
| `contracts/` | Solidity: NNTRewardSystem, DualMerkleClaim, gnnt.sol, etc. |
| `scripts/` | 17 Hardhat deploy/utility scripts |
| `artifacts/` | Hardhat compiled contract output |
| `cache/` | Hardhat build cache |
| `ignition/` | Hardhat Ignition deployment configs |
| `airdrop/` | NNT/GNNT airdrop tooling |
| `migrations/` | Old NNT database migrations |
| `test/` | Hardhat Solidity/JS tests |
| `tools/` | Legacy NNT tooling |
| `inputs/` | Legacy script input data |
| `uploads/` | Legacy upload storage |
| `Word/` | Legacy Word documents |
| `__pycache__/` | Python cache (legacy backend) |

### NOT moved (left in `nnt-token/`)
| Item | Reason kept |
|---|---|
| `nnt-expo/` | Active frontend app |
| `node_modules/` | Large Hardhat npm install — regenerable, untouched |
| `.venv/` / `venv/` | Large Python venvs — regenerable, untouched |
| `.gitignore` | Keep in place |
| `.env` / `.env.example` | May contain active BACKEND env var |

---

## 2. Archived — NNT-Only Content inside `nnt-token/nnt-expo/`

**Location:** `archive/nnt-legacy/nnt-expo-nnt-only/`

### App routes archived (`app-routes/`)
| Route | Reason |
|---|---|
| `app/(tabs)/airdrop.tsx` | NNT airdrop claim flow (was not in tab bar) |
| `app/(tabs)/rewards.tsx` | NNT/GNNT balance display (was not in tab bar) |
| `app/(tabs)/posts.tsx` | NNT post browser tab |
| `app/(tabs)/users.tsx` | NNT user list tab |
| `app/(tabs)/explore.tsx` | NNT explore tab (used PostList + usePosts) |
| `app/(tabs)/index.tsx` | NNT home post feed (saved as `index_nnt_original.tsx`) |
| `app/compose.tsx` | NNT post compose screen |
| `app/register.tsx` | NNT username registration screen |
| `app/admin/index.tsx` | NNT admin panel (Posts/Users/ad-stats — NNT-specific) |
| `app/claim/` | NNT on-chain token claim flow |
| `app/leaderboard/` | NNT leaderboard |
| `app/referral/` | NNT referral system |
| `app/account/` | NNT account page showing nnt/gnnt balances |
| `app/post/` | NNT post detail page |
| `app/user/` | NNT user profile page |

### Components archived (`components/`)
| Path | Reason |
|---|---|
| `src/components/airdrop/` | AirdropClaimer, AirdropStatus |
| `src/components/rewards/` | RewardsDashboard, ClaimButtons, RewardHistory |
| `src/components/posts/` | PostCard, PostFeed, PostDetail, PostStatus |
| `src/components/voting/` | VoteButtons, GodVoteButtons, VotingStatus |
| `src/components/users/` | UserCard, UserList, UserModerator, UserProfile, UserSearch, UserStats |
| `src/components/PostList.tsx` | NNT post list |

### Hooks archived (`hooks/`)
| Hook | Reason |
|---|---|
| `useTokenBalance.ts` | ERC-20 balance via ethers.js (only used by archived RewardsDashboard) |
| `useTransactions.ts` | ETH transaction sender (only used by archived useVoting) |
| `useVoting.ts` | NNT on-chain voting |
| `usePosts.ts` | NNT post feed hook |
| `usePostData.ts` | NNT post data loading |
| `usePostViewing.ts` | NNT post view tracking |
| `useUsers.ts` | NNT user list hook |
| `useAds.ts` | NNT ad-watching hook |
| `useAdminActions.ts` | NNT admin operations hook |

### Library archived (`lib/`)
| File | Reason |
|---|---|
| `src/lib/api.ts` | Legacy NNT API client (Points, nnt/gnnt token types, airdropClaimable, adComplete, getFeed, etc.) |

---

## 3. Deleted (Empty Stub Files)

These files were confirmed empty and provided no value:

- `src/hooks/useAirdrop.ts` — empty file, zero imports
- `src/hooks/useRewardClaims.ts` — empty file, zero imports

---

## 4. Active Files Modified

### `app/(tabs)/_layout.tsx`
- Removed: WalletConnect polyfill imports at top (`react-native-gesture-handler`, `@walletconnect/react-native-compat`, etc.)
- Removed tab declarations: `explore`, `claim/index`, `leaderboard/index`, `referral/index`, `account/index`
- Updated: "Home" tab title → "Gold Penny", now renders the new redirect `index.tsx`
- Kept: `settings` tab

### `app/(tabs)/index.tsx` *(replaced)*
- Old NNT post-feed home saved to archive as `index_nnt_original.tsx`
- New file: `Redirect` to `/gameplay` — routes users directly into the Gold Penny dashboard

### `src/components/TopStatusBar.tsx`
- Removed: `getApi` import, all NNT balance/ad-credit/claim-countdown display
- Kept: `useDebt` debt warning bar (shown only when player has outstanding debt > 0)

### `src/hooks/index.tsx`
- Removed re-exports: `useTokenBalance`, `useAds`, `usePosts`, `useTransactions`, `useVoting`, `useUsers`
- Kept: `useBackend`, `useRegistration`, `useWallet`, `useDebt`

### `src/constants/index.ts`
- Removed: `NNT_ADDRESS`, `GNNT_ADDRESS`, `NNT_DECIMALS`, `GNNT_DECIMALS`
- Removed: `WC_METADATA` with "NNT/GNNT — Sepolia Test Hub" branding
- Kept: `BACKEND`, `BUILD_TS`, `CHAIN_ID`, `RPC_URL`, `WC_PROJECT_ID`
- Updated: `WC_METADATA.name` → "Gold Penny", `description` → "Gold Penny mobile client"

### `nnt-expo/package.json`
- `"name"`: `"nnt-expo"` → `"goldpenny-expo"`

### `nnt-expo/app.json`
- `"name"`: `"nnt-expo"` → `"Gold Penny"` (display name only)
- **Unchanged** (intentionally): `slug`, `scheme`, `android.package`, EAS `projectId` — changing these would break OTA updates and app store entries

---

## 5. Active Gold Penny Files Preserved (Unchanged)

| Path | Description |
|---|---|
| `app/gameplay/` | Gold Penny game entry + player dashboard route |
| `app/admin/` | (empty dir — NNT admin was archived; GP admin needs future implementation) |
| `app/(tabs)/settings.tsx` | Gold Penny dev settings (backend URL override, admin token) |
| `app/_layout.tsx` | Root layout with WalletProvider + DebtProvider |
| `src/components/gameplay/` | 50+ Gold Penny dashboard cards (DailyBriefCard, etc.) |
| `src/components/layout/` | AppShell, ContentStack, PageContainer |
| `src/components/ui/` | PrimaryButton, SectionCard, etc. |
| `src/design/` | Gold Penny theme system |
| `src/lib/api/` | 15 Step 34-43 API clients (commitment → supplyChain) |
| `src/types/` | 15 Gold Penny type definition files |
| `src/hooks/useBackend.ts` | HTTP layer for all Gold Penny API calls |
| `src/hooks/useDebt.tsx` | Active debt tracking (DebtProvider) |
| `src/hooks/useWallet.ts` / `useWallet.tsx` | WalletConnect for wallet-based auth signing |
| `src/hooks/useRegistration.ts` | Wallet-based server auth flow |

---

## 6. Known Manual Review Items

| Item | Action Needed |
|---|---|
| `app/admin/` (now empty) | Implement Gold Penny admin panel — player management, marketplace oversight, etc. |
| `app.json` slug `"nnt-expo"` | Rename only when EAS project is reconfigured — would break OTA delivery otherwise |
| `app.json` scheme `"nnt"` | Rename only when deep-link handlers are updated across all platforms |
| `android.package "nntpress.com"` | Rename requires a new Play Store app entry |
| `node_modules/` at nnt-token root | Hardhat `node_modules` — safe to delete once legacy contracts are confirmed unused |
| `.venv/` / `venv/` at nnt-token root | Legacy Flask Python environments — safe to delete |
| `WalletConnect` in `app/_layout.tsx` | Review if wallet-based auth is still needed for Gold Penny, or if it can be removed |

---

## 7. File Count Summary

| Category | Count |
|---|---|
| nnt-token root files archived | 22 files + 13 dirs |
| nnt-expo app routes archived | 15 screens/dirs |
| nnt-expo components archived | 5 dirs + 1 file |
| nnt-expo hooks archived | 9 files |
| nnt-expo lib archived | 1 file |
| Empty stub files deleted | 2 |
| Active files modified | 7 |
| **TS compile errors after cleanup** | **0** |

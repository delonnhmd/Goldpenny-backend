# Step 47.1 — Production Build Readiness Pass for Expo iOS/Android

Status: Complete

## Files Reviewed

- `app.json`
- `eas.json`
- `package.json`
- `README.md`
- `src/constants/index.ts`
- `src/hooks/useWallet.tsx`
- `src/hooks/wallet-context.tsx`
- `src/lib/apiClient.ts`
- `src/lib/logger.ts`
- `src/assets/images/*`
- `assets/` (empty top-level folder)

## Files Updated

- `app.json`
- `eas.json`
- `package.json`
- `README.md`
- `.env.example`
- `src/constants/index.ts`
- `src/hooks/useWallet.tsx`
- `src/hooks/wallet-context.tsx`

## Config Issues Fixed

### 1. App identity was partly legacy / inconsistent
Before:
- Expo slug: `pft-expo`
- iOS bundle identifier: `com.goldpenny.pft`
- Android package: `com.goldpenny.pft`
- runtime version policy: `sdkVersion`
- package version: `1.0.0`
- app version/build values were not aligned cleanly

After:
- Expo name: `Gold Penny`
- Expo slug: `gold-penny-expo`
- deep link scheme: `goldpenny`
- iOS bundle identifier: `com.pennyfloat.goldpenny`
- Android package: `com.pennyfloat.goldpenny`
- app version: `1.0.1`
- iOS build number: `1.0.1`
- Android version code: `3`
- runtime version policy: `appVersion`

This is cleaner for store submission and future OTA update compatibility.

### 2. Expo config lacked store-facing asset references
Configured valid existing assets in `app.json`:
- icon: `./src/assets/images/icon.png`
- splash image: `./src/assets/images/splash-icon.png`
- Android adaptive icon foreground/background/monochrome images
- web favicon: `./src/assets/images/favicon.png`

All configured asset paths exist.

### 3. Expo config metadata was too thin for production readiness
Added:
- explicit app description
- portrait orientation
- explicit light UI style
- asset bundle patterns
- iOS `supportsTablet: false`

### 4. EAS production profile was not store-oriented
Before:
- production build used `distribution: internal`
- Android production build type was `apk`

After:
- production build uses `distribution: store`
- Android production build type is `app-bundle`
- production profile has `autoIncrement: true`
- development profile explicitly uses `developmentClient: true`
- EAS CLI minimum version added

This makes the repo structurally closer to a real store build flow.

### 5. Package metadata and scripts were missing basic build-readiness helpers
Updated `package.json`:
- renamed package to `gold-penny-expo`
- aligned version to `1.0.1`
- added `start:clear`
- added `typecheck`
- added `doctor`

## Asset / Config / Env Issues Found

### Asset findings
- The root `assets/` folder is effectively unused for Expo config.
- Real active images already existed under `src/assets/images/`.
- `app.json` previously did not reference them.

### Environment findings
Active public env keys in use:
- `EXPO_PUBLIC_BACKEND`
- `EXPO_PUBLIC_RPC_URL`
- `EXPO_PUBLIC_WC_PROJECT_ID`
- `EXPO_PUBLIC_DEBUG`

Fixes applied:
- added `.env.example`
- replaced starter README with app-specific env/setup/build docs
- clarified env behavior in `src/constants/index.ts`
- kept gameplay startup safe when `EXPO_PUBLIC_BACKEND` is missing: API calls fail with a clear error and Settings override still exists
- hardened wallet flow so missing `EXPO_PUBLIC_RPC_URL` now fails explicitly when wallet connect is invoked, instead of passing an empty RPC URL into provider setup

### Startup safety findings
- No localhost-only runtime dependency was found in the active Expo app config.
- Gameplay API startup already fails safely through `apiClient.ts` if backend URL is missing.
- Wallet connect still does not block app boot; it now fails clearly only when the wallet flow is actually used and env is incomplete.

## Bundle / Package Identity Status

Current production-facing identity after this pass:
- App name: `Gold Penny`
- Package name (`package.json`): `gold-penny-expo`
- Expo slug: `gold-penny-expo`
- Scheme: `goldpenny`
- iOS bundle identifier: `com.pennyfloat.goldpenny`
- Android package: `com.pennyfloat.goldpenny`
- Version: `1.0.1`
- iOS build number: `1.0.1`
- Android version code: `3`

Status: internally consistent and syntactically valid.

## Deep Link / Domain Status

Configured and verified:
- custom scheme: `goldpenny`
- WalletConnect metadata URL: `https://goldpenny.pennyfloat.com`
- primary docs updated to reflect:
  - `https://www.pennyfloat.com`
  - `https://goldpenny.pennyfloat.com`

Status:
- custom-scheme deep linking is configured
- hosted universal links / associated domains are not configured in repo, which is acceptable for this step and remains a manual deployment item

## Permissions / Platform Assumptions Review

Findings:
- no active camera/location/media permission config baggage found in Expo config
- no notifications permission config found in Expo config
- storage usage is expected via AsyncStorage
- wallet flow requires iOS `LSApplicationQueriesSchemes`, which remain intentionally configured
- no native `ios/` project folder exists in the current workspace, so the project is operating as config-driven Expo-managed/prebuild-ready rather than committed-native iOS

Status:
- no obvious unnecessary permission baggage remains in touched config files

## Validation Results

### Config validity
- `app.json` parsed successfully
- `npx expo config --type public` resolved successfully

### Asset path validity
- configured icon/splash/adaptive-icon/favicon paths exist

### Type / lint validation
- `npx tsc --noEmit`: passed
- `npx expo lint`: passed with 0 errors
- lint warnings improved from 12 to 10 by removing the unnecessary `redirectUrl` dependency warnings in the wallet hooks

### Naming integrity
Touched files scanned for:
- `nnt-token`
- `NNT`
- `GNNT`
- `nnt_`
- `nnt-expo`
- token-era leftovers
- old UI naming leakage

Result: clean in touched files.

## Remaining Manual Items Requiring Apple / Google / Portal Action

These are intentionally not committed in repo and still require manual setup outside the codebase:

1. Register/update the new bundle/package identifiers in Apple Developer / App Store Connect and Google Play:
- `com.pennyfloat.goldpenny`

2. Configure signing and release credentials:
- Apple certificates / provisioning
- Android keystore / Play App Signing

3. Confirm the final production backend URL and place it in the release environment.

4. Provide final production WalletConnect project ID and Sepolia RPC endpoint.

5. Replace current repo image assets with final store-approved artwork if branding changes are required.

6. If hosted universal links are desired, configure:
- `apple-app-site-association`
- Android asset links
- associated domains / verified app links

## Outcome

The Expo app is structurally cleaner and more production-safe after this pass:
- identity is coherent
- asset references are valid
- EAS production profile is closer to store output
- env usage is documented and safer
- no obvious repo-level iOS/Android build blocker remains in the active config

The next step can focus on deployment hardening rather than basic Expo config cleanup.

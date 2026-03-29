# Step 47.2 — EAS Profile Setup + Release Channel / Update Strategy Cleanup

Status: Complete

## Files Reviewed

- `app.json`
- `eas.json`
- `package.json`
- `README.md`
- `.env.example`
- `src/constants/index.ts`
- `src/hooks/useWallet.tsx`
- `src/hooks/wallet-context.tsx`

## Files Updated

- `app.json`
- `eas.json`
- `package.json`
- `README.md`

## Build Profiles Defined / Cleaned

### `development`
Purpose:
- internal development-client builds for device iteration and local debugging

Config:
- `developmentClient: true`
- `distribution: internal`
- `channel: development`
- `withoutCredentials: true`
- Android build type: `apk`

Rationale:
- keeps development fast and separate from store or tester-facing builds
- does not imply production credentials

### `preview`
Purpose:
- internal tester / QA builds

Config:
- `distribution: internal`
- `channel: preview`
- Android build type: `apk`

Rationale:
- supports a staging-style audience without mixing with production OTA traffic

### `production`
Purpose:
- store-distributed release candidates and production releases

Config:
- `distribution: store`
- `channel: production`
- `autoIncrement: true`
- Android build type: `app-bundle`

Rationale:
- clearer path to App Store / Play release work
- production audience is explicitly separated from dev/test audiences

### Submit profile
Added:
- `submit.production: {}`

Rationale:
- keeps the repo structure ready for future EAS submit usage without inventing portal credentials or store IDs

## Channel / Update Strategy Decisions

Defined channel naming strategy:
- `development`
- `preview`
- `production`

Properties of the strategy:
- simple and brand-clean
- no stale or old-project channel naming
- clear audience separation
- less risk of sending production OTA updates to preview/dev binaries

Channel rules documented in `README.md`:
- development builds -> development channel only
- preview builds -> preview channel only
- production builds -> production channel only

## Runtime Version Strategy Notes

Current runtime strategy:
- `runtimeVersion.policy = appVersion`

Why this was kept and reinforced:
- easy to understand
- production-safe for an Expo managed app with OTA updates
- binaries only receive OTA updates built for the same app version
- native-breaking changes should be accompanied by an app version bump, preventing incompatible OTA delivery to older binaries

This is a reasonable default for the app’s current maturity and simpler than custom runtime version logic.

## Update Behavior Cleanup

`app.json` updates config was made explicit:
- `enabled: true`
- `checkAutomatically: ON_LOAD`
- `fallbackToCacheTimeout: 0`

Meaning:
- OTA update behavior is now intentional rather than default-implicit
- app checks for updates on load
- startup still prefers immediate cached fallback safety

This keeps production update behavior understandable and less dependent on undocumented defaults.

## Env Separation Notes

No secrets were added to repo.

Documented assumptions instead:
- development can use local/dev backend values or Settings override
- preview should use non-production backend values when available
- production should use production backend and WalletConnect values only

This keeps the repo clean without inventing external EAS environment sets or credentials.

## Script Cleanup

Added release/build ergonomics to `package.json`:
- `config:public`
- `build:dev:android`
- `build:preview:android`
- `build:preview:ios`
- `build:prod:android`
- `build:prod:ios`
- `build:prod:all`

Result:
- profile usage is now discoverable from scripts instead of requiring contributors to remember raw EAS commands
- build intent is clearer for future release work

## Naming Integrity Findings

Touched files scanned for:
- `nnt-token`
- `NNT`
- `GNNT`
- `nnt_`
- `nnt-expo`
- stale release/build naming such as `pft-expo`
- old UI naming leakage

Result:
- clean in all touched build/release files

## Validation Results

### Config validity
- `app.json`, `eas.json`, and `package.json` all parse successfully
- `npx expo config --type public` resolves successfully

### Type / lint validation
- `npx tsc --noEmit`: passed
- `npx expo lint`: passed with 0 errors
- lint remains at 10 unrelated warnings outside this step’s touched files

### Coherence checks
- profile structure is coherent: development / preview / production
- channel names match the intended profile structure
- runtime version strategy remains simple and explicit
- update behavior is now explicit in config rather than implicit

## Remaining Manual Release Tasks Outside Repo

1. Configure EAS environment values for each audience if desired:
- development
- preview
- production

2. Set the actual non-secret runtime values per environment:
- `EXPO_PUBLIC_BACKEND`
- `EXPO_PUBLIC_RPC_URL`
- `EXPO_PUBLIC_WC_PROJECT_ID`

3. Configure Apple / Google signing and submission details.

4. If OTA publishing is used operationally, establish the team workflow for who can publish to:
- `development`
- `preview`
- `production`

5. If the project later needs stricter environment isolation, add explicit EAS environment-set usage or CI wrappers around the current profiles.

## Outcome

The repo now has a clearer and safer build/update path:
- development, preview, and production profiles are clearly defined
- update channels are clean and audience-separated
- runtime version strategy is understandable
- update behavior is explicit
- scripts are more usable for future iOS/Android release work

This leaves the project in a cleaner state for the next deployment-hardening step.

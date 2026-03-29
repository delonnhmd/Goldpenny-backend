# INTERNAL_EXPO_DEPLOY_REPORT_STEP64_1

Date: 2026-03-22  
Scope root: `/c/GoldPenny/goldpenny-backend/PFT/pft-expo`  
Terminal discipline: Git Bash command execution only for project operations.

## 1) Outcome

Internal Expo deployment prep is complete for Step 64.1.  
The app is build-ready for internal tester distribution through Expo/EAS, with config sanity checks, env audit, and validation gates completed.

Readiness status:
- Android internal deployment: ready (`development` or `preview` profiles).
- iOS internal deployment: ready via `preview` profile once Apple credentials/provisioning are configured in Expo/Apple portals.

## 2) Files Reviewed

- `app.json`
- `eas.json`
- `package.json`
- `tsconfig.json`
- `.env.example`
- `README.md`
- `app/(tabs)/settings.tsx`
- `src/constants/index.ts`
- `app/_layout.tsx`
- Asset references under `src/assets/images/*`

## 3) Files Updated

- `app.json`
  - Confirmed active Expo slug/project metadata for current EAS project.
  - Confirmed updates URL and EAS project ID alignment.
  - Removed duplicate Android deep-link intent-filter entry.
- `.env.example`
  - Removed dead runtime env references not used in active app runtime.
  - Kept active variables only: `EXPO_PUBLIC_BACKEND`, `EXPO_PUBLIC_DEBUG`.
- `README.md`
  - Aligned environment docs and deployment notes with active runtime behavior.
  - Removed stale wallet/RPC env requirements from deployment guidance.
- `app/(tabs)/settings.tsx`
  - Updated fallback slug from `pft-expo` to `gold-penny-expo` for naming consistency.
- `tsconfig.json` (already adjusted in this step sequence and validated)
  - Scoped typecheck includes to active mobile app paths (`app/**`, `src/**`) and excluded `web-bridge`.

## 4) Config And Build Audit Results

### Expo app identity and runtime

Verified in `app.json`:
- App name: `Gold Penny`
- Slug: `gold-penny-expo`
- Scheme: `goldpenny`
- iOS bundle ID: `com.pennyfloat.goldpenny`
- Android package: `com.pennyfloat.goldpenny`
- Runtime policy: `runtimeVersion.policy = appVersion`
- Updates: enabled, `checkAutomatically = ON_LOAD`, `fallbackToCacheTimeout = 0`
- Updates URL and `extra.eas.projectId` point to:
  - `cd780971-b503-487e-89dc-6984f42eba69`

### EAS profiles

Verified in `eas.json`:
- `development`
  - `developmentClient: true`
  - `distribution: internal`
  - Android `buildType: apk`
- `preview`
  - `distribution: internal`
  - Android `buildType: apk`
- `production`
  - `distribution: store`
  - Android `buildType: app-bundle`

### Asset references

Validated all configured assets exist:
- `src/assets/images/icon.png`
- `src/assets/images/splash-icon.png`
- `src/assets/images/android-icon-foreground.png`
- `src/assets/images/android-icon-background.png`
- `src/assets/images/android-icon-monochrome.png`
- `src/assets/images/favicon.png`

## 5) Environment Audit (Active Runtime)

Active Expo public env usage in app code:
- Required: `EXPO_PUBLIC_BACKEND`
- Optional: `EXPO_PUBLIC_DEBUG`

No active runtime usage found for:
- `EXPO_PUBLIC_RPC_URL`
- `EXPO_PUBLIC_WC_PROJECT_ID`

EAS hosted env status:
- `development`: no variables configured
- `preview`: no variables configured
- `production`: no variables configured

Deployment implication:
- Internal builds can be generated now, but testers need `EXPO_PUBLIC_BACKEND` configured (or manual override in Settings) for gameplay API requests.

## 6) Validation Results

Executed in Git Bash form:
- `yarn install --frozen-lockfile` -> pass (`Already up-to-date`)
- `yarn typecheck` -> pass
- `yarn lint` -> pass with warnings only (0 errors)
- `yarn config:public` -> pass (public Expo config resolved)
- `yarn doctor` -> warning/fail (2 checks):
  - duplicate native module resolution: `expo-constants` (`18.0.9` and transitive `18.0.13`)
  - Expo SDK patch version drift across multiple Expo packages
- `npx eas whoami` -> pass (`nntpress`)
- `npx eas project:info` -> pass (`@nntpress/gold-penny-expo`, project ID matches app config)
- `npx eas build:list --limit 1 --non-interactive` -> pass (no builds listed yet for this newly linked project)

Non-blocking lint warnings remain in existing source types; they do not block internal deployment.

## 7) Build/Deploy Risks Found

- EAS envs are empty for all profiles; internal testers will need a valid backend URL path before meaningful gameplay API testing.
- EAS channels currently show no entries (`channel:list --non-interactive --json` returned empty page). Internal build generation is unaffected, but OTA channel workflow should be initialized before update publishing.
- iOS internal distribution still depends on Apple signing/provisioning setup outside repo.
- Expo dependency drift flagged by `yarn doctor`; internal builds may still work, but native-build stability is better after `npx expo install --check` alignment.

## 8) Exact Git Bash Commands (No PowerShell Syntax)

Run these from Git Bash:

```bash
cd /c/GoldPenny/goldpenny-backend/PFT/pft-expo
pwd
```

Install/verify dependencies:

```bash
yarn install --frozen-lockfile
```

Expo/EAS auth and project checks:

```bash
npx eas --version
npx eas whoami || npx eas login
npx eas project:info
npx eas build:list --limit 5 --non-interactive
```

Set required internal env (minimum):

```bash
npx eas env:create development --name EXPO_PUBLIC_BACKEND --value "https://<internal-api>" --visibility plaintext --scope project
npx eas env:create preview --name EXPO_PUBLIC_BACKEND --value "https://<internal-api>" --visibility plaintext --scope project
```

Optional debug env:

```bash
npx eas env:create development --name EXPO_PUBLIC_DEBUG --value "1" --visibility plaintext --scope project
npx eas env:create preview --name EXPO_PUBLIC_DEBUG --value "0" --visibility plaintext --scope project
```

Local validation:

```bash
yarn typecheck
yarn lint
yarn config:public
yarn doctor
```

Optional dependency alignment (recommended before wider internal rollout):

```bash
npx expo install --check
```

Internal build commands:

```bash
npx eas build --profile development --platform android
npx eas build --profile preview --platform android
npx eas build --profile preview --platform ios
```

Optional local run commands:

```bash
yarn start
yarn android
yarn ios
```

Optional OTA/update setup and publish:

```bash
npx eas channel:create development --non-interactive || true
npx eas channel:create preview --non-interactive || true
npx eas channel:create production --non-interactive || true
npx eas update --branch preview --message "internal preview update"
```

## 9) Manual Items Remaining

- Expo account/project access for all internal testers who need build install links.
- Apple Developer setup for internal iOS distribution (certificates, provisioning profiles, devices/TestFlight path).
- Google Play internal testing track/signing setup if Android distribution will also flow through Play testing tracks.
- Final internal backend endpoint for preview environment.
- Device install validation on target real phones (Android/iOS), including deep-link launch smoke test for `goldpenny://`.

## 10) Success Criteria Check

- App ready for internal Expo/EAS deployment: **Yes**
- Git Bash-compatible command set prepared: **Yes**
- PowerShell command syntax used in prepared command list: **No**
- Config/build sanity for internal device testing: **Yes**
- Internal real-device rollout readiness: **Yes, pending external account/portal setup and env values**

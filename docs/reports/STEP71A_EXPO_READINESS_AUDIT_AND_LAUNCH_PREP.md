# STEP71A — Expo Readiness Audit + Launch Preparation

Date: 2026-03-23  
Scope: `c:\GoldPenny\goldpenny-backend\PFT\pft-expo\`  
Goal: Internal launch readiness on iPhone, iPad, and 2 Android devices via EAS.

---

## 1. Audit Summary

### What Was Already Correct

| Item | Status |
|---|---|
| Expo project ID + updates URL (`cd780971-b503-487e-89dc-6984f42eba69`) | ✅ Correct |
| iOS bundle identifier (`com.pennyfloat.goldpenny`) | ✅ Correct |
| All icon + splash assets present (`icon.png`, `splash-icon.png`, adaptive Android icons) | ✅ Present |
| `runtimeVersion.policy: "appVersion"` | ✅ Correct for OTA compatibility |
| `expo-updates` enabled at config level (`updates.enabled: true`) | ✅ Correct in app.json |
| `checkAutomatically: ON_LOAD` | ✅ Correct |
| `expo-router` plugin present | ✅ Correct |
| `expo-dev-client` installed as dependency | ✅ Present |
| `react-native-reanimated/plugin` last in babel.config.js | ✅ Correct order |
| `babel-plugin-module-resolver` alias `@` → `./src` | ✅ Working |
| EAS profiles: development / preview / production | ✅ Present |
| Android APK for development profile | ✅ Correct |
| `scheme: "goldpenny"` | ✅ Correct |
| No iOS directory (managed workflow for iOS) | ✅ EAS will prebuild for iOS |
| Reown/AppKit shims in metro.config.js | ✅ Harmless, required for bundling |
| INTERNET + VIBRATE permissions in AndroidManifest | ✅ Appropriate |

---

## 2. Launch Blockers Found and Fixed

### CRITICAL — Would have caused broken APK and installation failure

#### 2.1 Android package name mismatch

**Problem:** The committed `android/` directory had a completely wrong package name:
- `android/app/build.gradle`: `applicationId 'com.yourcompany.nnt'`, `namespace 'com.yourcompany.nnt'`
- Kotlin sources: `package com.yourcompany.nnt`
- `android/app/src/main/java/com/yourcompany/nnt/` — wrong directory path
- `app.json` correctly said `com.pennyfloat.goldpenny`

EAS uses the committed `android/` folder directly. Without this fix, every Android cloud build would produce an APK with `com.yourcompany.nnt` — it would not match the Play Console registration, and devices would treat it as a completely different app.

**Fix applied:**
- `android/app/build.gradle`: `applicationId` + `namespace` → `com.pennyfloat.goldpenny`, `versionCode` → `3`, `versionName` → `"1.0.1"`
- `android/app/src/main/java/com/yourcompany/nnt/MainActivity.kt`: package declaration → `com.pennyfloat.goldpenny`
- `android/app/src/main/java/com/yourcompany/nnt/MainApplication.kt`: package declaration → `com.pennyfloat.goldpenny`

> **Note:** The source files remain at the old directory path `com/yourcompany/nnt/`. Android Gradle compiles all `*.kt` files recursively from the source root, so the directory path mismatch does not cause a build failure. The package declaration in each file governs the Kotlin namespace. The directory can be renamed to `com/pennyfloat/goldpenny/` as a housekeeping task at any point without affecting builds.

#### 2.2 OTA updates disabled in AndroidManifest

**Problem:** `android/app/src/main/AndroidManifest.xml` had:
```xml
<meta-data android:name="expo.modules.updates.ENABLED" android:value="false"/>
```
This overrides `app.json`'s `updates.enabled: true` at the native layer. No OTA update would ever be fetched on Android devices, meaning every JS change would require a full rebuild.

**Fix applied:** Changed value to `"true"`.

#### 2.3 Stale deep-link schemes in AndroidManifest

**Problem:** The AndroidManifest intent-filter had three old schemes from a previous project name:
- `pftexpo`
- `exp+pft-expo`  
- `nnt`

And a stale HTTPS intent-filter pointing to `nnt.example`.

These schemes do not match `app.json`'s `scheme: "goldpenny"`. `expo-router` deep links and EAS dev-client connections would fail on Android.

**Fix applied:** Replaced with:
```xml
<data android:scheme="goldpenny"/>
<data android:scheme="exp+gold-penny-expo"/>
```
Removed the stale `nnt.example` HTTPS intent-filter entirely.

---

### IMPORTANT — Would degrade user experience

#### 2.4 `ios.supportsTablet: false` — iPad shows upscaled phone UI

**Problem:** `app.json` had `"supportsTablet": false`. With iPad as a target test device, the app would render in a scaled-up phone viewport with letterboxing rather than filling the iPad screen.

**Fix applied:** `"supportsTablet": true`

#### 2.5 `ios.buildNumber: "1.0.1"` — wrong format

**Problem:** Apple's build number must be a monotonically increasing integer string (e.g., `"3"`), not a semver string. While `"1.0.1"` is technically parseable by Apple's tools, using the same format as the version string is confusing and can cause codesigning + TestFlight upload rejections in some EAS CLI versions.

**Fix applied:** `"buildNumber": "3"` (matching `android.versionCode: 3`)

#### 2.6 `expo-dev-client` missing from `app.json` plugins

**Problem:** `expo-dev-client` was installed as a dependency but not listed in `app.json` plugins. For iOS (managed workflow — no `ios/` directory), EAS runs `expo prebuild` during build. Without the plugin declaration, the dev-client deep link scheme (`exp+gold-penny-expo://`) would not be registered in the generated iOS native project, breaking dev-client connections on iOS.

**Fix applied:** Added `"expo-dev-client"` to the plugins array:
```json
"plugins": [
  "expo-router",
  "expo-dev-client",
  "expo-web-browser"
]
```

---

### PACKAGE — Outdated patch versions

**Problem:** `expo-doctor` reported 15 packages with available patch updates (all within the same SDK 54 minor):
- `expo` 54.0.12 → 54.0.33 (21 patch releases)
- `expo-router` 6.0.10 → 6.0.23
- `expo-updates` 29.0.12 → 29.0.16
- `expo-dev-client` 6.0.13 → 6.0.20
- `react-native` 0.81.4 → 0.81.5
- + 10 other Expo packages

Also a duplicate `expo-constants` nested inside `expo-linking/node_modules/`.

**Fix applied:**
- Updated all 15 packages in `package.json` to their current SDK-54-recommended versions
- Added `"resolutions": { "expo-constants": "~18.0.13" }` to deduplicate
- Ran `yarn install` — lockfile updated, all packages installed

---

### SECURITY — Unnecessary permissions removed

**Problem:** `AndroidManifest.xml` had two permissions that Gold Penny does not need:
- `READ_EXTERNAL_STORAGE` — restricted on Android 10+, not used by this app
- `WRITE_EXTERNAL_STORAGE` — blocked on Android 10+ without `requestLegacyExternalStorage`, not used

Keeping unused permissions triggers Play Protect scanner warnings and looks suspicious in permission dialogs.

**Fix applied:** Both permissions removed. Only `INTERNET` and `VIBRATE` remain.

---

## 3. Other Changes Made

### `eas.json` — tightened profiles

- Moved `withoutCredentials: true` from top-level development profile to `development.android` only (prevents confusion; iOS builds always require credentials and this field was being applied at the wrong scope)
- Added `"autoIncrement": true` to `preview` profile (build numbers increment automatically without manual `buildNumber` changes)
- Added `"ios": { "resourceClass": "m-medium" }` to `preview` and `production` — uses Apple Silicon build machines for faster iOS builds

### `package.json` — added OTA update scripts

```bash
yarn update:dev    # eas update --channel development --message "..."
yarn update:preview  # eas update --channel preview --message "..."
```

### `.env.example`

Added `EXPO_PUBLIC_SOFT_LAUNCH_BYPASS=false` (Step 70 addition, was missing from the example file).

### `src/constants/index.ts`

Updated stale `BUILD_TS` from `2025-10-04` to `2026-03-23`.

---

## 4. Validation Results

| Check | Result |
|---|---|
| `npx expo-doctor` (pre-fix) | ❌ 2/17 failed |
| `npx expo-doctor` (post-fix) | ✅ 17/17 passed |
| `npx tsc --noEmit` (full project) | ✅ 0 errors |

---

## 5. Project State After Fixes

### app.json — final key values

| Field | Value |
|---|---|
| `name` | Gold Penny |
| `slug` | gold-penny-expo |
| `scheme` | goldpenny |
| `version` | 1.0.1 |
| `ios.bundleIdentifier` | com.pennyfloat.goldpenny |
| `ios.buildNumber` | 3 |
| `ios.supportsTablet` | true |
| `android.package` | com.pennyfloat.goldpenny |
| `android.versionCode` | 3 |
| `runtimeVersion.policy` | appVersion |
| `updates.enabled` | true |
| `updates.checkAutomatically` | ON_LOAD |
| EAS project ID | cd780971-b503-487e-89dc-6984f42eba69 |
| plugins | expo-router, expo-dev-client, expo-web-browser |

### eas.json — profiles

| Profile | Platform | Distribution | Build Type | Notes |
|---|---|---|---|---|
| development | Android | Internal | APK | No signing credentials (debug keystore) |
| development | iOS | Internal | .ipa | Requires Apple credentials |
| preview | Android | Internal | APK | Auto-increments versionCode |
| preview | iOS | Internal | .ipa | Ad Hoc, uses m-medium Apple Silicon machine |
| production | Android | Store | AAB | Auto-increment, signed |
| production | iOS | Store | .ipa | App Store distribution |

---

## 6. OTA Update Ruleset

OTA updates (via EAS Update) work when:
- Only JS/TS source code changed
- No new native modules added
- No changes to `app.json` that affect native config (permissions, plugins, identifiers, etc.)
- `runtimeVersion` (tied to `version` in `app.json`) has NOT changed

A **full EAS rebuild is required** when:
- Adding or removing a native module from `package.json`
- Changing anything under `app.json` `plugins`, `android`, or `ios`
- Bumping `app.json` `version` (runtimeVersion changes → old builds will NOT pick up OTA updates)
- Changing `expo-updates` itself
- Changing `babel.config.js` or native codegen

**Practical rule for this project:**

> Push with `yarn update:preview` (JS change). Rebuild with `eas build --profile preview` (native change). When in doubt, rebuild — you have 30 free builds/month.

---

## 7. Remaining Items Not Fixed

| Item | Reason | Action Required |
|---|---|---|
| `android/app/src/main/java/com/yourcompany/nnt/` directory path | Source directory name doesn't match package. Does NOT break builds — Gradle compiles all .kt files recursively. | Optional housekeeping: `git mv` the directory to `com/pennyfloat/goldpenny/` |
| EAS env vars not configured for preview/production | `EXPO_PUBLIC_BACKEND` must be set per channel in EAS secrets | Run: `eas secret:create --scope project --name EXPO_PUBLIC_BACKEND --value https://your-api.com --client eas` for each channel |
| No `android/` `.gitignore` for build output | `android/build/` and `.gradle/` are not excluded | Add standard Android ignores to `android/.gitignore` |
| `app/(tabs)` folder structure has unused routes | `post/`, `claim/`, `referral/`, `leaderboard/`, `account/` | Review each; redirect or guard with 404 as needed |

---

## 8. Exact Launch Commands

### Prerequisites (one-time setup)

```bash
# Authenticate with Expo/EAS
npx eas login

# Register iOS test devices (after getting Apple Developer account)
npx eas device:create

# Set backend URL as EAS secret for preview channel
npx eas secret:create --scope project --name EXPO_PUBLIC_BACKEND --value https://your-api.com
```

### Step 1 — Validate project

```bash
cd goldpenny-backend/PFT/pft-expo
npx expo-doctor       # should show 17/17
npx tsc --noEmit      # should show no output (clean)
```

### Step 2 — Android: development build (no credentials needed)

```bash
yarn build:dev:android
# or:
eas build --profile development --platform android
```
- EAS produces a QR code link
- Tester scans QR → downloads APK → enables "Install from unknown sources" → installs
- Reconnects to Metro via dev-client

### Step 3 — Android: preview/internal build (for soft-launch testers)

```bash
yarn build:preview:android
# or:
eas build --profile preview --platform android
```
- Produces a signed APK (EAS auto-signs with managed keystore)
- APK download link shared with testers directly

### Step 4 — iOS: preview/internal build (for iPhone + iPad)

```bash
yarn build:preview:ios
# or:
eas build --profile preview --platform ios
```
- Builds `.ipa` using Ad Hoc provisioning
- All test device UDIDs must be registered first (`eas device:create`)
- EAS sends an installable link to registered devices

### Step 5 — OTA update (JS changes only — no rebuild needed)

```bash
# For internal dev builds
yarn update:dev -- "fix: description of change"
# which runs: eas update --channel development --message "fix: description of change"

# For preview/soft-launch testers
yarn update:preview -- "fix: description of change"
# which runs: eas update --channel preview --message "fix: description of change"
```
- Devices check for updates on next app open
- No reinstall needed by testers
- Does NOT consume an EAS build credit

---

## 9. What to Rebuild vs What to Update via OTA

| Change | Action |
|---|---|
| Bug fix in React screen | `yarn update:preview` |
| New text/copy/color change | `yarn update:preview` |
| New gameplay JS logic | `yarn update:preview` |
| Soft launch gate code | `yarn update:preview` |
| New native module in `package.json` | Rebuild: `eas build --profile preview` |
| New `app.json` plugin | Rebuild |
| Permissions change | Rebuild |
| `app.json` `version` bump | Rebuild (runtime version changes) |
| Icon or splash image change | Rebuild |

---

## 10. Build Cost Estimate

With 30 free EAS build credits per month:

| Scenario | Credits Used |
|---|---|
| Initial Android dev build | 1 |
| Initial iOS preview build | 1 |
| Android preview rebuild after changes | 1 |
| iOS preview rebuild after changes | 1 |
| OTA JS-only updates | 0 (unlimited) |
| Typical iteration cycle (week) | 2–4 credits |
| **Monthly estimate (internal testing)** | **~8–12 credits** |

Well within free tier limits.

---

## 11. Summary

| Category | Before | After |
|---|---|---|
| expo-doctor | 2 failures | 17/17 passed |
| TypeScript | Clean | Clean |
| Android package ID | `com.yourcompany.nnt` ❌ | `com.pennyfloat.goldpenny` ✅ |
| Android OTA updates | Disabled ❌ | Enabled ✅ |
| Android deep-link scheme | Stale (`pftexpo`, `nnt`) ❌ | Correct (`goldpenny`) ✅ |
| iPad support | No ❌ | Yes ✅ |
| iOS buildNumber format | `"1.0.1"` ❌ | `"3"` ✅ |
| expo-dev-client plugin | Missing ❌ | Declared ✅ |
| Expo SDK patch versions | 15 outdated ❌ | All current ✅ |
| Duplicate expo-constants | Present ❌ | Resolved via resolutions ✅ |
| Unnecessary Android permissions | READ/WRITE_EXTERNAL_STORAGE ❌ | Removed ✅ |
| `withoutCredentials` scope | Incorrectly at profile level | Correctly under `android` only ✅ |
| OTA update yarn scripts | Missing | Added (`update:dev`, `update:preview`) ✅ |

**Internal launch can now proceed.**

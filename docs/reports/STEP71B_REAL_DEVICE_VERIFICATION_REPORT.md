# STEP 71B — Real Device Build, Install, and Verification
**Gold Penny — Internal Launch Execution**
Date: 2026-03-23
Step: 71B (follows 71A Expo Readiness Audit)
Status: LOCAL VALIDATION COMPLETE — AWAITING DEVICE BUILDS

---

## Execution Log

| Phase | Command | Result | Time |
|---|---|---|---|
| Dependency install | `yarn install --frozen-lockfile` | ✅ Already up-to-date (0.44s) | 2026-03-23 |
| SDK health | `npx expo-doctor` | ✅ 17/17 checks passed | 2026-03-23 |
| TypeScript | `npx tsc --noEmit` | ✅ PASSED (0 errors) | 2026-03-23 |
| Lint | `yarn lint` | ⚠→✅ 1 error found + fixed (see Section 0) | 2026-03-23 |
| Android build | `yarn build:dev:android` | ⏳ PENDING | — |
| iOS build | `yarn build:preview:ios` | ⏳ PENDING | — |
| OTA test | `yarn update:preview` | ⏳ PENDING | — |

---

## Section 0 — Blocker Found and Fixed During Validation

### React Hook Rules Violation in GameplayLoopScaffold

**File:** `src/features/gameplayLoop/GameplayLoopScaffold.tsx`  
**Line:** 125 (before fix)  
**Lint rule:** `react-hooks/rules-of-hooks`  
**Severity:** Error (lint exit 1)  

**Root cause:** `useMemo` was declared after an early `return` triggered by the `gateBlocked` check. React requires all hooks to be called unconditionally in the same order on every render. This would cause a React runtime invariant violation in production if the `gateBlocked` branch was ever triggered, potentially crashing the gate screen.

**Fix applied:** Moved `const bottomNavItems = useMemo(...)` to before the `if (gateBlocked)` return. The `useMemo` depends only on `navigateTo` and `onboardingActive`, both of which are fully in scope before the early return. The early return itself was moved to just after the `useMemo` closes.

**Diff summary:**
```
// Before (incorrect — hook called conditionally):
  useEffect(...) // ensureRoute
  if (gateBlocked) return <SoftLaunchGate .../>     ← early return
  const bottomNavItems = useMemo(...)               ← hook AFTER early return ❌
  return <AppShell ...>

// After (correct — hook always called):
  useEffect(...) // ensureRoute
  const bottomNavItems = useMemo(...)               ← hook always executes ✅
  if (gateBlocked) return <SoftLaunchGate .../>     ← early return safe here
  return <AppShell ...>
```

**Post-fix validation:**
- `yarn lint` → ✅ 0 errors, 10 warnings (all cosmetic — `Array<T>` style + unused imports)
- `npx tsc --noEmit` → ✅ PASSED

---

## Overview

Step 71A completed all Expo + EAS config corrections.
Step 71B executes the internal launch: builds for real devices, installs, verifies gameplay end-to-end on iPhone, iPad, and two Android phones, tests OTA delivery, and produces a go/no-go recommendation.

**Devices:**
| Slot | Platform | Build Profile |
|---|---|---|
| Android #1 | Android | `development` (APK, no credentials) |
| Android #2 | Android | `development` or `preview` APK |
| iPhone | iOS | `preview` (internal .ipa) |
| iPad | iOS | `preview` (internal .ipa, same build) |

---

## Section 1 — Pre-Build Requirements

### 1.1 Required Accounts & Memberships

| Item | Requirement | Status |
|---|---|---|
| EAS account | `nntpress` Expo account | ⚠️ Must confirm login before build |
| Apple Developer Program | $99/yr — required for iOS sideload | ⚠️ Required before iOS build |
| Google Play (optional) | Free — not needed for APK sideload | ✅ Not required for APK sideload |
| Backend host | `EXPO_PUBLIC_BACKEND` EAS project secret | ⚠️ Required before any real API calls |

### 1.2 One-Time Pre-Build Steps (run once, not per device)

All commands run from `c:\GoldPenny\goldpenny-backend\PFT\pft-expo`

```bash
# Step 1 — Verify EAS login
npx eas whoami
# Expected output: nntpress
# If not logged in:
npx eas login

# Step 2 — Register iOS test device UDIDs  [MANUAL — YOU MUST SUPPLY DEVICE UDIDs]
#
#   Option A: device plugged into Mac via USB
npx eas device:create
#   EAS will prompt: "Enter UDID". You can find it in:
#     - Xcode → Window → Devices and Simulators → (select device) → Identifier
#     - Settings → General → VPN & Device Management → Trust
#     - Apple Configurator 2 → device info panel
#
#   Option B: generate an OTA registration URL (no USB needed)
npx eas device:create --type url
#   EAS prints a URL. Open it in Safari on the device. Tap Install. Done.
#   Repeat for iPhone, then iPad.

# Step 3 — Set the backend URL as an EAS project secret  [MANUAL — SUPPLY YOUR URL]
#   Replace https://your-api-host.com with the deployed backend URL
npx eas secret:create \
  --scope project \
  --name EXPO_PUBLIC_BACKEND \
  --value https://your-api-host.com

# Step 4 — Confirm both secrets/devices are saved
npx eas secret:list
npx eas device:list
```

### 1.3 What Is Configured vs What You Must Supply

| Item | Pre-configured in repo | You must provide |
|---|---|---|
| EAS project ID `cd780971-...` | ✅ in `app.json` `extra.eas.projectId` | — |
| EAS owner `nntpress` | ✅ in `app.json` `owner` | — |
| iOS bundle ID `com.pennyfloat.goldpenny` | ✅ in `app.json` | — |
| Android package `com.pennyfloat.goldpenny` | ✅ in `build.gradle` + `app.json` | — |
| Android APK no-credential build | ✅ `eas.json` development profile | — |
| iOS m-medium resource class | ✅ `eas.json` preview + production | — |
| OTA update channel mapping | ✅ `eas.json` channel per profile | — |
| Build scripts | ✅ all in `package.json` | — |
| iPhone UDID | ❌ | You: `eas device:create` |
| iPad UDID | ❌ | You: `eas device:create` |
| Backend URL (`EXPO_PUBLIC_BACKEND`) | ❌ | You: `eas secret:create` |
| EAS login session | ❌ | You: `eas login` if expired |

> **Important:** Without `EXPO_PUBLIC_BACKEND` the app will still launch and be playable in mock data mode, but the soft launch gate will fail to reach the backend and will show the gate screen (unless `EXPO_PUBLIC_SOFT_LAUNCH_BYPASS=true` is set). For internal testing of the full flow, the secret must be set.

> **Note:** Steps 2–3 only need to be done once. Subsequent builds and OTA updates reuse stored credentials automatically.

---

## Section 2 — Build Execution Plan

All commands run from:
```
cd c:\GoldPenny\goldpenny-backend\PFT\pft-expo
```

### 2.1 Step-by-step order

#### Phase A — Dependency & Validation (local, no cloud build credits)

```bash
# A1. Verify packages are installed at locked versions
yarn install --frozen-lockfile

# A2. Doctor — validate SDK + dependency health (must be 17/17)
yarn doctor
# equivalent: npx expo-doctor

# A3. TypeScript check — must pass with 0 errors
yarn typecheck
# equivalent: npx tsc --noEmit

# A4. Lint — must pass with 0 errors (warnings OK)
yarn lint
```

**Confirmed results (2026-03-23):**
- `yarn install --frozen-lockfile` → ✅ "Already up-to-date. Done in 0.44s"
- `yarn doctor` → ✅ "17/17 checks passed. No issues detected!"
- `yarn typecheck` → ✅ PASSED (0 errors)
- `yarn lint` → ✅ 0 errors after hook fix (Section 0); 10 cosmetic warnings remain

> All four checks are green. Safe to proceed to cloud builds.

---

#### Phase B — Android Build (no Apple credentials needed)

The `development` profile emits a sideloadable APK with `withoutCredentials: true`, meaning zero keystore setup is required. Install directly on Android without Google Play.

```bash
# B1. Android development APK — no credentials, installable as APK
# Use this for Android #1 (fastest, zero keystore)
yarn build:dev:android
# equivalent: eas build --profile development --platform android --non-interactive
```

For Android #2 (or if you want a shareable link with auto-increment):

```bash
# B2. Android preview APK — signed, internal distribution
yarn build:preview:android
# equivalent: eas build --profile preview --platform android
```

> **Recommendation for minimal build credit use:** Run `build:dev:android` for both Android phones. One build produces one APK that installs on any Android device — you do not need to submit two separate builds.

**Where to get the APK after the build completes:**
EAS CLI prints:
```
✔ Build finished. Android build artifact:
  https://expo.dev/accounts/nntpress/projects/gold-penny-expo/builds/<BUILD_ID>
```
Open that URL in a browser → click "Download build artifact" → get `.apk`.

**Install on Android devices — step by step:**
```
1. On the device:
   Settings → Security → "Install unknown apps" → enable for your browser or Files app.

2. Transfer the APK (choose one):
   Option A — Download from EAS QR code:
     - Open EAS build URL in browser on the device
     - Scan QR code shown in the EAS builds dashboard
     - Tap INSTALL when prompted

   Option B — ADB install (device plugged into computer):
     adb install gold-penny-<build-id>.apk

   Option C — Google Drive / email:
     Upload APK, open on device, tap to install

3. Tap INSTALL when the system installer dialog appears.
   You may see "Unknown source" warning — tap Install Anyway.

4. After install: open the app from the launcher.
   The dev-client launcher will appear briefly, then connect to the
   EAS Update channel automatically (no local server needed for internal testing).
```

**Likely blockers and diagnosis:**
| Symptom | Cause | Fix |
|---|---|---|
| "App not installed" | APK signed with debug key conflicting with existing install | Uninstall previous version first |
| "Parse error" | APK corrupted during download | Re-download |
| Launcher stuck on "Looking for updates" | No EAS Update published to `development` channel yet | Run `yarn update:dev -- "initial"` or use `preview` profile instead |
| Network error on first launch | `EXPO_PUBLIC_BACKEND` not set in this build | Set secret and rebuild, or test in mock mode |

---

#### Phase C — iOS Build (requires Apple Developer Program + registered UDIDs)

**Apple-side prerequisites (must be satisfied before running this command):**
```
1. Apple Developer Program membership active ($99/yr).
2. iPhone and iPad UDIDs registered via: npx eas device:create
   (EAS will automatically create/update provisioning profiles to include them)
3. eas login confirms nntpress account.
4. EXPO_PUBLIC_BACKEND secret set (npx eas secret:create ...)
```

```bash
# C1. iOS preview IPA — internal distribution
# Covers registered iPhone + iPad with a single build
yarn build:preview:ios
# equivalent: eas build --profile preview --platform ios
```

What EAS does automatically:
1. Creates/renews a Distribution Certificate for your Apple account (first time only)
2. Generates an Ad Hoc Provisioning Profile covering your registered device UDIDs
3. Builds on Apple Silicon (m-medium) → typically 10–20 min
4. Returns an install URL + QR code for the `.ipa`

**Install on iPhone / iPad — step by step:**
```
Option A (recommended — no Mac needed):
  1. On each iOS device, open Safari (not Chrome — must be Safari).
  2. Navigate to the EAS build URL or scan the QR code from the EAS dashboard.
  3. EAS serves an itms-services:// manifest.
  4. Tap "Install" when iOS prompts.
  5. Trust the developer cert:
     Settings → General → VPN & Device Management → [your Apple account] → Trust.
  6. Open Gold Penny from the Home Screen.

Option B (Apple Configurator 2):
  1. Download the .ipa from the EAS build page.
  2. Open Apple Configurator 2 on a Mac.
  3. Connect device via USB.
  4. Drag the .ipa onto the device in Configurator.
```

**iOS-specific blockers and diagnosis:**
| Symptom | Cause | Fix |
|---|---|---|
| Build fails: "No matching profiles" | UDIDs not registered before build | Run `eas device:create`, then rebuild |
| Build fails: "Certificate error" | Apple cert needs renewal or new key | EAS handles this automatically on next build attempt |
| "Unable to Download App" on device | UDID not in provisioning profile | Confirm device was registered before this build; rebuild |
| App installs but crashes immediately | Missing `EXPO_PUBLIC_BACKEND` secret at build time + softLaunch fetch crash | Secret must be set before build so it's embedded |
| "Untrusted Developer" on first open | Normal iOS behavior for Ad Hoc builds | Trust the cert in Settings → General → VPN & Device Management |

---

#### Phase D — OTA Update Test

> See Section 4 for the full OTA verification procedure.

```bash
# D1. Publish a JS-only update to the preview channel after devices are installed
yarn update:preview -- "test: OTA delivery verification"
# equivalent: eas update --channel preview --message "test: OTA delivery verification"
```

---

### 2.2 Build Command Reference Summary

| Command | Profile | Platform | Output | Credentials |
|---|---|---|---|---|
| `yarn build:dev:android` | development | Android | APK | None required |
| `yarn build:preview:android` | preview | Android | APK | Keystore (EAS managed) |
| `yarn build:preview:ios` | preview | iOS | IPA | Apple cert + provisioning |
| `yarn build:prod:android` | production | Android | AAB | Keystore (EAS managed) |
| `yarn build:prod:ios` | production | iOS | IPA | Apple cert + App Store |
| `yarn update:preview -- "msg"` | preview | Both | JS bundle | None |
| `yarn update:dev -- "msg"` | development | Both | JS bundle | None |

---

## Section 3 — Device Install Verification Checklist

Use this checklist for every device being verified. Mark each item P (Pass), F (Fail), or N/A.

### Checklist Template

```
Device: ___________________________
OS Version: _______________________
Build Profile Used: ________________
Install Date: _______________________

[ ] APK/IPA downloaded successfully
[ ] App installs without errors
[ ] App icon appears on home screen
[ ] App launches without crash on first open
[ ] Splash screen displays correctly (dark bg #0f172a)
[ ] Onboarding flow appears on first launch
[ ] Onboarding completes / can be dismissed
[ ] Player name / setup screen works
[ ] Day 1 gameplay loop loads
[ ] Player can take at least one work action
[ ] Day 1 can be settled / completed
[ ] End-of-day summary appears with earnings
[ ] Cash / stress / health stats display correctly
[ ] Day 2 loads after Day 1 settlement
[ ] Bottom tab bar is visible and navigable
[ ] No route errors / blank screens on navigation
[ ] Deep link goldpenny:// resolves (optional test)
[ ] App returns from background correctly
[ ] No crash after 5 minutes of idle
[ ] OTA update is received (after Section 4 test)
[ ] BUILD_TS label shows updated timestamp after OTA

Notes (UI / bugs / crashes):
_______________________________________________
_______________________________________________
```

### Tablet-Specific Items (iPad only)

```
[ ] Layout fills tablet width — not stretched phone UI
[ ] supportsTablet: true is effective (no letterboxing)
[ ] Tap targets are not oversized / misaligned on large display
[ ] Text legibility at tablet scale is acceptable
[ ] Orientation lock is respected (portrait forced per app.json)
```

### Android-Specific Items

```
[ ] Back button (gesture or hardware) works correctly
[ ] App does not request unexpected permissions on install
[ ] Deep link scheme goldpenny:// registers in Android settings
[ ] Status bar color matches app theme
[ ] No ANR (app not responding) dialogs during gameplay
```

### iOS-Specific Items

```
[ ] Home indicator area is not blocked by UI elements
[ ] Safe area insets respected on notch / Dynamic Island
[ ] No permission dialog appears unexpectedly on first run
[ ] TestFlight or direct install completes without trust warning
```

---

## Section 4 — OTA Verification Procedure

### Purpose

Verify that EAS Update can push a JS-only change to installed apps without requiring a new native build. This confirms the OTA pipeline used for soft launch patch delivery works correctly.

### The Change

The OTA test modifies a visible, non-functional label in `src/constants/index.ts`. The `BUILD_TS` constant is already displayed in some debug/dev surfaces, and this change will be detectable in any screen that shows a build timestamp.

**Before (current value):**
```ts
export const BUILD_TS = '2026-03-23T00:00:00Z';
```

**After (OTA marker):**
```ts
export const BUILD_TS = '2026-03-23T12:00:00Z';
```

This is a pure JS change — no native module, no new package, no schema change. It qualifies as a compatible OTA update under the `appVersion` runtime policy.

### OTA Test Steps

```bash
# Step 1 — Make the visible marker change
# File: src/constants/index.ts
# Change line 5 from:
#   export const BUILD_TS = '2026-03-23T00:00:00Z';
# To:
#   export const BUILD_TS = '2026-03-23T12:00:00Z';
#
# This is a one-character JS change. No native code. No new imports.

# Step 2 — Confirm it still typechecks (sanity check before upload)
cd "C:\GoldPenny\goldpenny-backend\PFT\pft-expo"
yarn typecheck

# Step 3 — Publish to the preview channel
yarn update:preview -- "test: OTA BUILD_TS marker 2026-03-23T12"
# EAS output to expect:
#   ✓ Published! Update group ID: <uuid>
#   Channel:         preview
#   Runtime version: 1.0.1
#   Platform:        android + ios

# Step 4 — On EACH installed device (Android + iPhone + iPad):
#   a. Swipe the app out of the multitasking switcher (fully closed)
#   b. Reopen the app from the launcher
#   c. expo-updates fires checkForUpdateAsync on app load (per app.json checkAutomatically: ON_LOAD)
#   d. The new JS bundle downloads silently
#   e. Force-close the app a SECOND time
#   f. Reopen — the new bundle is now active

# Step 5 — Verify the update is active:
#   Check any screen that surfaces BUILD_TS
#   Expected: '2026-03-23T12:00:00Z' (not T00)
#   If using a development build: Expo DevTools > Updates shows new manifest ID

# Step 6 — Revert BUILD_TS after OTA is confirmed:
# Change '2026-03-23T12:00:00Z' → '2026-03-23T00:00:00Z'
# The revert does NOT need to be published as another OTA —
# it will be included naturally in the next full build.
```

**Why two app opens are needed:**  
Under `checkAutomatically: ON_LOAD`, updates are fetched on the first open and applied on the *next* cold start. This is intentional — it avoids interrupting the user's current session. The two-close-and-reopen sequence is the expected verification flow.

**OTA rollback if something breaks:**
```bash
# List recent updates on the preview channel
npx eas update:list --branch preview

# Roll back to a previous update group
npx eas update:rollback --branch preview --group <previous-update-group-id>
```

### OTA Compatibility Rules

| Allowed in OTA | Not Allowed in OTA (requires new build) |
|---|---|
| JS/TS logic changes | Adding new native modules |
| UI text, colors, layout | Changing `app.json` plugins |
| New screens / routes | expo SDK version bump |
| API call changes | New native permissions |
| Bug fixes in existing code | Changes to `android/` or `ios/` native code |

### OTA Failure Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Update not received after reopen | Channel mismatch | Confirm app was built with `preview` profile |
| "Update unavailable" | runtimeVersion mismatch | Rebuild the app — JS bundle compiled against different native version |
| App crashes after OTA | New code uses uninstalled native module | Revert via `eas update --rollback` or push a fix update |
| Update downloaded but not applied | App not fully closed | Force-close and reopen |

---

## Section 5 — Launch Issue Log Format

Use one entry per device per test session. Store in a shared doc or paste into a GitHub issue.

```markdown
## Device Test Log — Gold Penny Internal Launch

### Entry
- **Date:** YYYY-MM-DD
- **Tester:** [name or initials]
- **Session:** Step 71B internal verification

---

**Device:** [e.g., iPhone 15 Pro]
**OS Version:** [e.g., iOS 18.3.1]
**Build Profile:** [development | preview]
**Build ID:** [from EAS dashboard, e.g., xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx]
**App Version:** 1.0.1 (build 3)

**Install Result:** [✅ Success | ❌ Failed — describe]

**Gameplay Result:**
- Onboarding: [✅ Passed | ❌ failed at step: ___ ]
- Day 1 completed: [✅ | ❌]
- Summary shown: [✅ | N/A]

**UI Issues:**
- [ ] None
- [ ] Describe: ___________________

**Crash / Bug Notes:**
- [None observed]
- [Bug: describe exact screen, action, error message or crash type]

**OTA Update Received:** [✅ Yes / ❌ No / — Not tested]

**Overall:**  [✅ PASS — ready for soft launch | ⚠️ CONDITIONAL — minor issues |  ❌ BLOCK — critical issue]

---
```

---

## Section 6 — Build & Test Results

*This section is pre-populated with known state after Step 71A. Update each row as real device builds complete.*

### 6.1 Pre-Build Validation Results (Step 71B execution — 2026-03-23)

| Check | Command | Result | Notes |
|---|---|---|---|
| Dependency install | `yarn install --frozen-lockfile` | ✅ PASS | Already up-to-date, 0.44s |
| SDK health | `npx expo-doctor` | ✅ PASS | 17/17 checks passed |
| TypeScript | `npx tsc --noEmit` | ✅ PASS | 0 errors |
| Lint | `yarn lint` | ✅ PASS (after fix) | 0 errors, 10 cosmetic warnings |
| Hook rule fix | `GameplayLoopScaffold.tsx` | ✅ FIXED | `useMemo` moved before early return |
| Android package ID | `build.gradle` + Kotlin | ✅ FIXED (71A) | `com.pennyfloat.goldpenny` |
| iOS buildNumber format | `app.json` | ✅ FIXED (71A) | `"3"` (integer string) |
| OTA enabled | `AndroidManifest.xml` | ✅ FIXED (71A) | `"true"` |
| Deep-link schemes | `AndroidManifest.xml` | ✅ FIXED (71A) | `goldpenny`, `exp+gold-penny-expo` |
| `expo-dev-client` in plugins | `app.json` | ✅ FIXED (71A) | Added |
| `supportsTablet` | `app.json` | ✅ FIXED (71A) | `true` |

### 6.2 Build Results (fill as builds complete)

| Build | Profile | Platform | EAS Build ID | Result | APK/IPA URL |
|---|---|---|---|---|---|
| Android #1 | development | Android | — | PENDING | — |
| Android #2 | development | Android | — | PENDING | — |
| iPhone | preview | iOS | — | PENDING | — |
| iPad | preview | iOS | — | PENDING | (same IPA as iPhone) |

### 6.3 Device Verification Matrix (fill after installs)

| Device | Install | Launch | Onboarding | Day 1 | Summary | OTA | Result |
|---|---|---|---|---|---|---|---|
| Android #1 | — | — | — | — | — | — | PENDING |
| Android #2 | — | — | — | — | — | — | PENDING |
| iPhone | — | — | — | — | — | — | PENDING |
| iPad | — | — | — | — | — | — | PENDING |

### 6.4 OTA Verification Result

| Channel | Update Published | Android #1 Received | Android #2 Received | iPhone Received | iPad Received |
|---|---|---|---|---|---|
| preview | PENDING | — | — | — | — |

---

## Section 7 — Soft Launch Go / No-Go

### Criteria

| Criterion | Required | Status |
|---|---|---|
| Android APK installs cleanly | Yes | PENDING |
| iOS .ipa installs cleanly | Yes | PENDING |
| App launches without crash | Yes | PENDING |
| Onboarding completes | Yes | PENDING |
| Day 1 settles correctly | Yes | PENDING |
| OTA update delivered | Yes | PENDING |
| Backend responds to API requests | Yes | PENDING — requires `EXPO_PUBLIC_BACKEND` set |
| No layout breakage on iPad | Yes | PENDING |
| No data loss on app reopen | Yes | PENDING |

### Blockers Found (update as tests run)

| # | Device | Issue | Severity | Resolution |
|---|---|---|---|---|
| — | — | — | — | — |

### Recommendation

```
CURRENT STATE: LOCAL VALIDATION COMPLETE — GO FOR DEVICE BUILDS

Pre-build validation: ✅ GO
  - yarn install --frozen-lockfile : PASS
  - npx expo-doctor                : 17/17
  - npx tsc --noEmit               : PASS (0 errors)
  - yarn lint                      : PASS (0 errors after hook fix)
  - Hook blocker in GameplayLoopScaffold: FIXED

Device verification: ⏳ PENDING (awaiting build submission)

Required manual steps before builds:
  1. npx eas whoami  →  confirm nntpress session
  2. npx eas device:create  →  register iPhone UDID
  3. npx eas device:create  →  register iPad UDID
  4. npx eas secret:create --scope project --name EXPO_PUBLIC_BACKEND --value <url>
  5. npx eas secret:list  →  confirm secret is stored

Android build (zero prerequisites beyond eas login):
  yarn build:dev:android

iOS build (after steps 1–5 above):
  yarn build:preview:ios

OTA test (after both builds install on devices):
  Edit src/constants/index.ts → BUILD_TS T00 → T12
  yarn update:preview -- "test: OTA BUILD_TS marker"
  Force-close + reopen twice on each device
  Confirm BUILD_TS shows T12

Move to Step 72 (soft launch) only after:
  - At least 1 Android device passes full checklist
  - At least iPhone passes full checklist
  - OTA update received on at least 1 device
  - No startup crashes or Day 1 gameplay blockers logged
```

---

## Section 8 — Remaining Housekeeping (Non-Blocking)

These items do not block the internal launch but should be resolved before public release.

| Item | Priority | Action |
|---|---|---|
| Kotlin source directory `com/yourcompany/nnt/` | Low | `git mv android/app/src/main/java/com/yourcompany/nnt android/app/src/main/java/com/pennyfloat/goldpenny` |
| Stale app routes (`/post`, `/claim`, `/referral`) | Medium | Add 404 redirect or `notFound()` guard |
| `.env.local` not in `.gitignore` | Check | Confirm `.env.local` is in `.gitignore` |
| Apple provisioning cert renewal process | Low | Document before cert expiry (1 year from first build) |
| Backend URL (`EXPO_PUBLIC_BACKEND`) in EAS secrets | **Required** | `npx eas secret:create --scope project --name EXPO_PUBLIC_BACKEND --value ...` |

---

## Section 9 — Quick Reference

### All EAS Build Commands

```bash
# From: c:\GoldPenny\goldpenny-backend\PFT\pft-expo

# Android (no credentials)
yarn build:dev:android

# Android (signed APK)
yarn build:preview:android

# iOS (requires Apple Dev account + UDIDs registered)
yarn build:preview:ios

# OTA push (JS-only, no rebuild)
yarn update:preview -- "description of change"
yarn update:dev -- "description of change"

# List active secrets
npx eas secret:list

# List registered devices
npx eas device:list

# Check current update status
npx eas update:list --branch preview
```

### Runtime Version Policy Note

The `runtimeVersion.policy` is `"appVersion"` (from `app.json`).  
This means:
- OTA updates are only delivered to builds with **the same `version` string** (`"1.0.1"`).
- If `version` changes to `"1.0.2"`, a new native build is required before OTA updates apply.
- Incrementing `versionCode` / `buildNumber` alone does **not** break OTA compatibility.

### Channel → Build Profile Mapping

| EAS Update Channel | Built With Profile | When to Use |
|---|---|---|
| `development` | `development` | Active development, dev-client APK/IPA |
| `preview` | `preview` | Internal testers, no App Store |
| `production` | `production` | App Store / Google Play |

---

*Report prepared for Step 71B — Gold Penny Internal Launch Execution.*
*All pre-build conditions confirmed by Step 71A Expo Readiness Audit (2026-03-23).*

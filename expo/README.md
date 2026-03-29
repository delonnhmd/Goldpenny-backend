# Gold Penny Expo App

Mobile app for the Gold Penny gameplay experience from Penny Float.

Primary domains:
- Main website: https://www.pennyfloat.com
- Gold Penny app domain: https://goldpenny.pennyfloat.com

## Environment

Create a local `.env` file from `.env.example` before running the app.

Runtime environment variables:
- `EXPO_PUBLIC_BACKEND`: required for gameplay API requests
- `EXPO_PUBLIC_DEBUG`: optional, set to `1` to enable verbose client logging

Behavior when env is missing:
- missing `EXPO_PUBLIC_BACKEND`: gameplay API requests fail with a clear runtime error and Settings can still provide an override URL
- missing `EXPO_PUBLIC_DEBUG`: app behavior is unchanged and debug logging stays off

## Privacy And Permissions

Current app behavior:
- local storage is used for remembered player ID, advanced connection settings, session continuity, and recent redacted diagnostics
- network access is used for gameplay API requests and OTA updates
- no active camera, photo library, location, clipboard, or background-processing feature is part of the app experience

Diagnostics posture:
- recent diagnostics store only short messages, source labels, and timestamps for production troubleshooting
- sensitive values such as tokens and backend URLs are redacted before persistence

## Development

Install dependencies:

```bash
yarn install
```

Run the app:

```bash
yarn start
```

Useful scripts:

```bash
yarn typecheck
yarn lint
yarn doctor
yarn android
yarn ios
```

## Build Readiness

Production identity:
- App name: `Gold Penny`
- Expo slug: `goldpenny-expo`
- Deep link scheme: `goldpenny`
- iOS bundle identifier: `com.pennyfloat.goldpenny`
- Android package: `com.pennyfloat.goldpenny`

Asset paths configured in `app.json`:
- icon: `./src/assets/images/icon.png`
- splash: `./src/assets/images/splash-icon.png`
- android adaptive icon assets under `./src/assets/images/`
- web favicon: `./src/assets/images/favicon.png`

## Release Strategy

Build profiles:
- `development`: internal development-client builds for local debugging and device iteration
- `preview`: internal tester builds for QA / staging-style validation
- `production`: store-distributed builds for App Store / Play release candidates and production release

EAS channels:
- `development`
- `preview`
- `production`

Channel rules:
- development builds receive only `development` channel OTA updates
- preview builds receive only `preview` channel OTA updates
- production builds receive only `production` channel OTA updates

Runtime version strategy:
- `runtimeVersion.policy = appVersion`
- OTA updates are compatible only with binaries built from the same app version
- native-breaking changes should ship with a version bump so older binaries do not receive incompatible updates

Expo Updates behavior:
- updates are enabled
- update check occurs on load
- cached bundle fallback timeout is `0` for immediate startup safety

Useful release commands:

```bash
yarn config:public
yarn build:dev:android
yarn build:preview:android
yarn build:preview:ios
yarn build:prod:android
yarn build:prod:ios
yarn build:prod:all
```

Environment separation assumptions:
- development profile can target local/dev backends through `.env` or Settings override
- preview profile should use non-production backend values when available
- production profile should use production backend values and conservative logging defaults
- no secrets are stored in this repo; final environment values belong in EAS or local secure configuration

## Manual Release Items

These are intentionally not stored in the repo and still require Apple / Google / Expo portal work:
- App Store Connect app record and certificates
- Google Play app record and signing setup
- Final production backend URL
- Final store artwork / screenshots / listing copy
- Optional universal-link / associated-domain setup for hosted deep links
- App Store privacy answers and Google Play data-safety answers based on the final production backend and analytics posture

# Store Compliance Pass Report Step 47.4

## Goal

Reduce App Store and Google Play review risk for the active Gold Penny Expo app by tightening store-facing metadata, privacy-sensitive surfaces, permission-related footprint, wallet wording, and stale brand leftovers in active files.

## Files Reviewed

- `app.json`
- `package.json`
- `yarn.lock`
- `README.md`
- `.env.example`
- `app/_layout.tsx`
- `app/(tabs)/settings.tsx`
- `app/(tabs)/index.tsx`
- `app/gameplay/index.tsx`
- `src/constants/index.ts`
- `src/lib/logger.ts`
- `src/lib/apiClient.ts`
- `src/hooks/useWallet.tsx`
- `src/hooks/useRegistration.ts`
- `src/hooks/index.tsx`

## Files Updated

- `app.json`
- `package.json`
- `yarn.lock`
- `README.md`
- `app/(tabs)/settings.tsx`
- `app/(tabs)/index.tsx`
- `app/gameplay/index.tsx`
- `src/constants/index.ts`
- `src/lib/logger.ts`
- `src/lib/apiClient.ts`
- `src/hooks/useWallet.tsx`
- `src/hooks/useRegistration.ts`
- `src/hooks/index.tsx`

## Metadata And Identity Issues Found

- App description was technically correct but too bare for store-facing metadata.
- Settings showed build identity but did not surface the approved Penny Float domains.
- Wallet metadata used a third-party WalletConnect logo URL instead of first-party brand alignment.
- A stale legacy NNT comment remained in the active home-tab file.

## Metadata And Identity Cleanup

- Updated Expo description to `Gold Penny is a daily strategy game from Penny Float.`
- Kept app name, slug, scheme, package, and bundle identifiers aligned with the current production naming.
- Added Penny Float website and Gold Penny game site rows to the Settings identity section.
- Replaced the WalletConnect metadata description with first-party app wording.
- Replaced the WalletConnect metadata icon URL with a Gold Penny domain URL.
- Removed the stale legacy NNT comment from the active home-tab route.

## Privacy And Permission Issues Found

- `expo-image-picker` was still installed even though no active code path used it.
- That dependency created unnecessary permission-related baggage for future native builds and review questions.
- Diagnostics were already redacted in storage, but wallet debug logs still emitted raw deep-link and account details when debug logging was enabled.

## Privacy And Permission Cleanup

- Removed `expo-image-picker` from dependencies and regenerated `yarn.lock`.
- Confirmed no active camera, media-library, location, clipboard, or background-processing feature is used by the app.
- Kept wallet functionality optional and user-initiated.
- Tightened diagnostics redaction to also catch keys like `nonce`, `projectId`, and `header`.
- Replaced raw wallet debug logging with safer summary logs.
- Kept user-facing diagnostics limited to severity, source, short message, and timestamp.

## Crypto / Web3 Review-Risk Cleanup

- Reworded wallet-related config comments to describe optional external-wallet behavior rather than low-level implementation detail.
- Changed user-facing missing-wallet-config errors to `Wallet connection is not available in this build.` instead of exposing raw environment variable names.
- Adjusted the Sepolia chain label to `Sepolia Testnet` for clearer and more accurate external-wallet prompts.
- Removed overly technical `WalletConnect` wording from user-visible copy where safer wording was available.

## Settings And UI Copy Cleanup

- Renamed `Network and Admin Overrides` to `Advanced Connection Settings`.
- Reworded the section summary so it reads as support / QA tooling rather than an exposed developer panel.
- Renamed labels to:
  - `Server URL Override`
  - `Support Access Token`
  - `Support Account Address`
- Updated save/reset success messaging to be less internal and more professional.
- Clarified the gameplay entry screen text so it explains local player ID storage in plain language.
- Simplified the diagnostics card display so it does not expose internal action keys in the visible UI.

## Diagnostics Safety Review

- Recent diagnostics already stored redacted context only.
- Added stronger key redaction coverage in `src/lib/logger.ts`.
- Removed raw WalletConnect URI and account logging from debug output.
- Confirmed Settings only shows non-sensitive diagnostic summaries.

## Naming And Domain Integrity

- Checked touched active files for `nnt-token`, `NNT`, `GNNT`, stale token-era language, and domain inconsistency.
- Removed active-file stale NNT references from:
  - `app/(tabs)/index.tsx`
  - `src/hooks/index.tsx`
- Confirmed touched compliance files now use Penny Float / Gold Penny naming consistently.
- Confirmed active review-facing domains align with:
  - `https://www.pennyfloat.com`
  - `https://goldpenny.pennyfloat.com`

## Validation

- `npx expo config --type public`
  - Resolved successfully
  - Confirmed no image-picker plugin baggage remained in active config
  - Confirmed iOS query schemes no longer include stale `zerion`
- `npx tsc --noEmit`
  - Passed
- `npx expo lint`
  - Passed with 0 errors and 10 pre-existing warnings

## Remaining Manual Items For App Store / Play Console Later

- Final App Store Connect metadata, screenshots, and age-rating answers
- Final Google Play listing copy, screenshots, and content-rating answers
- App Store privacy questionnaire answers based on the final production backend and any future analytics/crash tooling
- Google Play data-safety form answers based on the final production backend and data handling policy
- Final confirmation that the hosted favicon or icon URL used for wallet metadata is reachable from the production domain
- Final review of whether external-wallet functionality and Sepolia testnet usage are acceptable for the intended store release strategy

## Outcome

The active Expo app is cleaner and lower-risk for future store submission work:

- metadata is more professional and brand-aligned
- unnecessary permission-related dependency baggage was removed
- diagnostics are safer for production exposure
- wallet-related wording is more precise and less review-hostile
- touched active files no longer carry obvious old token-era naming leftovers

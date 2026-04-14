# STEP 95 Auth, Account Foundation, Business CTA, and Nav Cleanup

## Overview

Step 95 adds a real account/session layer, keeps it separate from gameplay state, fixes the missing starter-business CTA, removes outdated page-level navigation buttons, and adds a fresh-start player creation flow so new accounts do not inherit old local test state.

This step now follows the split below:

- Account/Auth layer
  - user identity
  - sign up / log in / log out
  - session restore
  - password reset
- Game Profile layer
  - player profile id
  - cash, debt, health, stress
  - job selection and day progression
  - business ownership and operations

One account maps to one player profile, but they are no longer treated as the same object.

## Auth Architecture

### Backend

- `users` remains the auth/account table.
- `players` remains the gameplay profile table with `user_id` as the one-to-one link.
- Auth responses now allow `player_profile` to be `null`.
- Register and login no longer auto-create a player profile.
- New endpoint:
  - `POST /auth/player-profile`
  - Creates exactly one clean Day 1 player profile for the signed-in account.

### Fresh Start Player Creation

The fresh-start create-player flow now does this:

- Creates a brand new `players` row linked to the signed-in account
- Initializes starter baseline values from the suburban starter preset
- Creates Day 1 daily state
- Leaves `main_job` unset
- Leaves employment history empty
- Leaves settlement history empty
- Leaves stale local cached player ids cleared until a real profile exists

This prevents:

- auto-linking to old `Player1`
- auto-loading broken local cached gameplay state
- duplicate player creation on repeated login

## Account ↔ Player Linking Design

### Rule

- `users.id` identifies the account
- `players.user_id` identifies the linked gameplay profile
- one account can have zero or one player profile during the fresh-start step
- once created, the same player profile is reused on later logins and session restore

### Session Behavior

- authenticated + no player profile
  - route to `/auth/create-player`
- authenticated + player profile
  - route to `/gameplay/loop/{playerId}/brief`
- unauthenticated
  - route to `/auth/login`

Gameplay routes now redirect to the linked account player id if a mismatched route id is supplied.

## New Auth Screens

Added or updated:

- `expo/app/auth/login.tsx`
- `expo/app/auth/signup.tsx`
- `expo/app/auth/forgot-password.tsx`
- `expo/app/auth/reset-password.tsx`
- `expo/app/auth/create-player.tsx`
- `expo/app/account/index.tsx`

### Create New Player Screen

New behavior:

- shown after signup or login if the account has no linked player profile
- presents a single clear CTA: `Create New Player`
- creates a clean baseline profile
- routes into the standard gameplay/onboarding flow afterward

## Session Flow

Implemented in the auth provider and route entrypoints:

- session persists in AsyncStorage
- app restores session on launch
- unauthenticated users are sent to auth
- authenticated users bypass login
- authenticated users without a profile are sent to create-player
- logout clears auth session and cached last player id

## Business CTA Visibility Fix

### Problem Before

Starter business cards showed:

- cost
- current cash
- need amount

But if the player could afford the business, there was still no visible action button.

### Behavior After

On the Business screen starter cards now compute:

- `cost_xgp`
- `cashOnHand`
- `need = max(cost - cash, 0)`

If `need <= 0`:

- show enabled CTA
- example: `Open Fruit Shop`

If `need > 0`:

- show disabled CTA
- example: `Need 513.91 more XGP`

### Open Business Action

The CTA now calls the auth-protected business open endpoint:

- `POST /business/open`

On success it:

- deducts startup cost
- creates ownership state
- refreshes gameplay bundle
- updates business/dashboard UI
- shows success feedback

Example:

- Before:
  - Fruit Shop cost `500.00 XGP`
  - Cash `686.09 XGP`
  - Need `0.00 XGP`
  - No button shown
- After:
  - Fruit Shop cost `500.00 XGP`
  - Cash `686.09 XGP`
  - Need `0.00 XGP`
  - `Open Fruit Shop` button visible and enabled

## Removed Redundant Buttons

### Business Screen

Removed:

- `Back To Market`
- `Open Brief`

### Brief Screen

Removed:

- `Go To Dashboard`

### Result

- Business cards and business actions are now the focus
- Brief only shows settlement / next-day actions when relevant
- no redundant footer nav clutter remains

## Before / After Examples

### New Account

Before:

- signup/login could immediately auto-bootstrap gameplay state
- player creation was not explicit
- stale local state could interfere with fresh testing

After:

- signup creates account session only
- login restores account session only
- if no profile exists, user sees `Create New Player`
- new player starts from clean Day 1 baseline

### Business Screen

Before:

- affordable starter business had no action button
- footer used page-to-page nav buttons

After:

- affordable starter business shows clear `Open ...` CTA
- unaffordable starter business shows clear unmet requirement text
- footer clutter removed

### Brief Screen

Before:

- `Go To Dashboard` footer action could appear

After:

- only real day-flow actions remain
- settlement and next-day actions stay available when needed

## Files Changed

### Backend

- `backend/app/models/user.py`
- `backend/alembic/versions/20260414_0027_auth_account_foundation.py`
- `backend/app/api/auth.py`
- `backend/tests/test_auth_account_flow.py`

### Expo App / Frontend

- `expo/app/_layout.tsx`
- `expo/app/index.tsx`
- `expo/app/account/index.tsx`
- `expo/app/auth/_layout.tsx`
- `expo/app/auth/login.tsx`
- `expo/app/auth/signup.tsx`
- `expo/app/auth/forgot-password.tsx`
- `expo/app/auth/reset-password.tsx`
- `expo/app/auth/create-player.tsx`
- `expo/app/gameplay/index.tsx`
- `expo/app/gameplay/[playerId].tsx`
- `expo/app/gameplay/loop/[playerId]/_layout.tsx`
- `expo/app/(tabs)/settings.tsx`
- `expo/src/features/auth/AuthShell.tsx`
- `expo/src/features/auth/context.tsx`
- `expo/src/features/auth/index.ts`
- `expo/src/features/auth/storage.ts`
- `expo/src/features/gameplayLoop/GameplayLoopScaffold.tsx`
- `expo/src/features/gameplayLoop/screens/BriefScreen.tsx`
- `expo/src/features/gameplayLoop/screens/BusinessScreen.tsx`
- `expo/src/lib/api/auth.ts`
- `expo/src/lib/api/business.ts`
- `expo/src/lib/apiClient.ts`
- `expo/src/types/auth.ts`
- `expo/src/types/gameplay.ts`

## Validation Results

### Automated

- `yarn typecheck` in `expo`: passed
- `python -m py_compile backend/app/api/auth.py`: passed
- `pytest backend/tests/test_auth_account_flow.py -q`: passed

### Verified by Code Path

- new signup no longer auto-creates a player profile
- login no longer creates duplicate player profiles
- explicit `Create New Player` creates exactly one clean linked player profile
- new player baseline starts with:
  - starter cash
  - starter debt
  - baseline health/stress
  - Day 1 daily state
  - no main job assigned
  - no employment history
- gameplay routes now require valid auth + linked player mapping
- Business screen shows CTA when affordable
- redundant nav buttons removed from Business and Brief

## Notes

- This step intentionally does not rewrite shift execution, salary posting, rideshare rules, stress logic, or end-of-day settlement.
- Auth now only decides who the account is and which player profile to load.
- Gameplay continues to own all runtime simulation state.

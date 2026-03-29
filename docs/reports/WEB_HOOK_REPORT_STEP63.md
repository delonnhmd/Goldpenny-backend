# WEB_HOOK_REPORT_STEP63.md

## Step 63 Summary

Implemented a dedicated **Gold Penny Web Bridge** in `web-bridge/` as a lightweight Next.js companion app.

Design intent is preserved:

- Web reads and displays backend state.
- Mobile remains the gameplay runtime.
- Backend remains source of truth.
- No gameplay loop or economy logic duplicated on web.

## Pages Created

- `/` (landing)
  - Defines web companion role and boundary.
  - CTA links to `/game`, `/connect`, and deep-link back to mobile.
- `/game` (Gold Penny dashboard)
  - Displays Daily Brief (headline + summary).
  - Displays player snapshot (Cash, Debt, Net Flow).
  - Displays opportunity/warning highlights.
  - Displays optional portfolio summary + top holdings.
  - Includes robust partial-data and missing-data states.
  - Includes `Continue in App` deep link.
- `/connect` (wallet placeholder)
  - Connect Wallet placeholder button and state transitions (`idle`, `connecting`, `ready`).
  - Explicitly disables claim/transfer/token execution logic.

## Endpoints Used (Read-Only)

- `GET /briefs/player/{player_id}/latest`
- `GET /day/summary/{player_id}`
- `GET /economy-presentation/player/{player_id}/summary`
- `GET /stocks/quotes`
- `GET /stocks/portfolio/{player_id}`

Notes:

- These are the same backend surfaces already consumed by mobile (or aligned contracts).
- No action execution endpoint is called from the web bridge.

## Deep Link Setup

- Implemented deep link target: `goldpenny://gameplay`
- Player-aware format supported: `goldpenny://gameplay?playerId=<uuid>`
- Configurable via:
  - `NEXT_PUBLIC_GOLDPENNY_DEEP_LINK`

## Wallet Prep (No Full Implementation)

Implemented wallet-prep UI only:

- `Connect Wallet` button
- Placeholder connection states
- No claim logic
- No on-chain transfer logic
- No gameplay mutation path

## Domain Integration Details

Prepared for deployment to `goldpenny.pennyfloat.com`:

- SEO metadata configured in `app/layout.tsx`
  - title template
  - description
  - Open Graph metadata
  - canonical alternates
- Canonical host configurable:
  - `NEXT_PUBLIC_GOLDPENNY_CANONICAL_HOST` (default `goldpenny.pennyfloat.com`)
- Route coverage confirmed in build output:
  - `/`
  - `/game`
  - `/connect`
- Deployment steps documented in `web-bridge/README.md`:
  - build/start commands
  - DNS mapping to host provider
  - HTTPS/SSL enablement

Operational note:

- This step includes deploy-ready configuration and documentation.
- Live DNS + SSL cutover to `goldpenny.pennyfloat.com` still requires host-console changes.

## Clean Boundary Enforcement

Boundary enforcement is implemented directly in UI and data layer:

- UI copy explicitly states web is read-only.
- Data loader only calls read endpoints.
- No gameplay action calls from web.
- Deep-link path encourages continuation in mobile runtime.

## Naming Check

Verified in the new web bridge code:

- No legacy token aliases are present in routes, UI copy, or config.
- Gold Penny naming is used consistently.

## Validation Results

Executed in `web-bridge/`:

1. `npm run lint`
   - Result: pass
2. `npm run typecheck`
   - Result: pass
3. `npm run build`
   - Result: pass
   - Routes generated: `/`, `/connect`, `/game`

Additional hardening:

- Updated Next.js to patched `15.5.14` to avoid known vulnerability warning from initial scaffold version.

## Files Added/Updated (Step 63)

- `web-bridge/package.json`
- `web-bridge/package-lock.json`
- `web-bridge/next.config.ts`
- `web-bridge/tsconfig.json`
- `web-bridge/next-env.d.ts`
- `web-bridge/.eslintrc.json`
- `web-bridge/.gitignore`
- `web-bridge/.env.example`
- `web-bridge/README.md`
- `web-bridge/app/layout.tsx`
- `web-bridge/app/globals.css`
- `web-bridge/app/page.tsx`
- `web-bridge/app/game/page.tsx`
- `web-bridge/app/connect/page.tsx`
- `web-bridge/components/BridgeShell.tsx`
- `web-bridge/components/WalletPrepCard.tsx`
- `web-bridge/lib/config.ts`
- `web-bridge/lib/formatters.ts`
- `web-bridge/lib/types.ts`
- `web-bridge/lib/bridgeApi.ts`

# Gold Penny Web Bridge

Lightweight web companion for Gold Penny.

## Purpose

- Read and display backend state (Daily Brief, player snapshot, optional portfolio).
- Provide a wallet-connect placeholder for future integration.
- Deep-link users back into the mobile app.

This bridge intentionally does **not** execute gameplay logic.

## Routes

- `/` - Landing + role boundary.
- `/game` - Daily Brief + player snapshot + optional portfolio.
- `/connect` - Wallet-prep placeholder UI.

## Environment

Copy `.env.example` to `.env.local`:

- `GOLDPENNY_BACKEND_URL` - backend base URL (required if no query override).
- `GOLDPENNY_DEFAULT_PLAYER_ID` - default player UUID for `/game`.
- `NEXT_PUBLIC_GOLDPENNY_DEEP_LINK` - app deep link (defaults to `goldpenny://gameplay`).
- `NEXT_PUBLIC_GOLDPENNY_CANONICAL_HOST` - canonical host (defaults to `goldpenny.pennyfloat.com`).

## Development

```bash
npm install
npm run dev
```

Open:

- `http://localhost:3000/`
- `http://localhost:3000/game?playerId=<player-uuid>`

## Deployment

1. Build and start:

```bash
npm run build
npm run start
```

2. Configure custom domain `goldpenny.pennyfloat.com` on your host.
3. Point DNS (`CNAME` or equivalent) to the host-provided target.
4. Enable automatic HTTPS/SSL certificate issuance.
5. Verify route handling for `/`, `/game`, and `/connect`.

## Data Endpoints

- `GET /briefs/player/{player_id}/latest`
- `GET /day/summary/{player_id}`
- `GET /economy-presentation/player/{player_id}/summary`
- `GET /stocks/quotes`
- `GET /stocks/portfolio/{player_id}`

If any endpoint is unavailable, the UI remains functional and surfaces partial-data warnings.
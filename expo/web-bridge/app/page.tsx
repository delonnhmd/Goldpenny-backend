import Link from 'next/link';

import BridgeShell from '@/components/BridgeShell';
import { buildGameplayDeepLink, resolvePlayerId } from '@/lib/config';

export default function LandingPage() {
  const defaultPlayerId = resolvePlayerId();
  const gameHref = defaultPlayerId ? `/game?playerId=${encodeURIComponent(defaultPlayerId)}` : '/game';
  const deepLink = buildGameplayDeepLink(defaultPlayerId);

  return (
    <BridgeShell
      title="Mobile-first companion for Gold Penny"
      subtitle="Use web for Daily Brief, read-only snapshot, and future wallet access while gameplay stays in the mobile runtime."
    >
      <section className="content-grid">
        <article className="content-card content-col-6">
          <h3>Web MVP Role</h3>
          <ul className="copy-list">
            <li>Show Daily Brief context from backend summaries.</li>
            <li>Show player cash, debt, and net flow snapshot.</li>
            <li>Show optional market portfolio readout.</li>
            <li>Prepare a wallet connection surface for future integration.</li>
            <li>Deep link players back into the Gold Penny app.</li>
          </ul>
        </article>

        <article className="content-card content-col-6">
          <h3>Boundary Guardrail</h3>
          <ul className="copy-list">
            <li>Web does not execute gameplay actions.</li>
            <li>Web does not simulate economy logic.</li>
            <li>Backend remains the single source of truth.</li>
            <li>Mobile remains the primary gameplay client.</li>
          </ul>
        </article>

        <article className="content-card content-col-8">
          <h3>Start Step 63 Dashboard</h3>
          <p>
            Open the game dashboard to pull the latest backend data for your player ID. Use query params if you need to override
            backend URL or player target for soft launch testing.
          </p>
          <div className="button-row">
            <Link href={gameHref} className="primary-button">
              Open /game
            </Link>
            <Link href="/connect" className="secondary-button">
              Open /connect
            </Link>
            <a href={deepLink} className="secondary-button">
              Continue in App
            </a>
          </div>
        </article>

        <article className="content-card content-col-4">
          <h3>Domain Target</h3>
          <p>
            Canonical host for this bridge is <strong>goldpenny.pennyfloat.com</strong> with HTTPS and direct route handling for
            <code> /</code>, <code> /game</code>, and <code> /connect</code>.
          </p>
        </article>
      </section>
    </BridgeShell>
  );
}
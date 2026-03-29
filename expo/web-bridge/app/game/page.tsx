import Link from 'next/link';

import BridgeShell from '@/components/BridgeShell';
import { buildGameplayDeepLink } from '@/lib/config';
import { formatSignedXgp, formatXgp } from '@/lib/formatters';
import { loadBridgeSnapshot } from '@/lib/bridgeApi';

export const dynamic = 'force-dynamic';

interface SearchParams {
  [key: string]: string | string[] | undefined;
}

interface GamePageProps {
  searchParams?: Promise<SearchParams>;
}

async function resolveSearchParams(searchParams: Promise<SearchParams> | undefined): Promise<SearchParams> {
  if (!searchParams) return {};
  return searchParams;
}

function readParam(searchParams: SearchParams, key: string): string | null {
  const value = searchParams[key];
  if (Array.isArray(value)) return value[0] ?? null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  return null;
}

export default async function GamePage({ searchParams }: GamePageProps) {
  const resolvedParams = await resolveSearchParams(searchParams);
  const playerIdOverride = readParam(resolvedParams, 'playerId');
  const backendOverride = readParam(resolvedParams, 'backend');

  const result = await loadBridgeSnapshot({
    playerIdOverride,
    backendOverride,
  });

  const deepLink = buildGameplayDeepLink(result.playerId);

  return (
    <BridgeShell
      title="Gold Penny Dashboard"
      subtitle="Live read-only snapshot from backend endpoints used by mobile. Use this for companion visibility, not gameplay execution."
    >
      <section className="content-grid">
        <article className="content-card content-col-8">
          <h3>Load Bridge Data</h3>
          <form action="/game" method="get" className="form-grid">
            <div className="field-group field-player">
              <label htmlFor="playerId">Player ID</label>
              <input
                id="playerId"
                name="playerId"
                defaultValue={result.playerId ?? ''}
                placeholder="UUID from backend player profile"
              />
            </div>
            <div className="field-group field-backend">
              <label htmlFor="backend">Backend URL (Optional Override)</label>
              <input
                id="backend"
                name="backend"
                defaultValue={backendOverride ?? ''}
                placeholder={result.backendBaseUrl ?? 'https://your-backend-host'}
              />
            </div>
            <div className="button-row">
              <button type="submit" className="primary-button">
                Refresh Snapshot
              </button>
              <a href={deepLink} className="secondary-button">
                Continue in App
              </a>
            </div>
          </form>
        </article>

        <article className="content-card content-col-4">
          <h3>Boundary</h3>
          <div className="boundary-note">
            <p>
              <strong>Web:</strong> read-only display.
            </p>
            <p>
              <strong>Mobile:</strong> gameplay actions.
            </p>
            <p>
              <strong>Backend:</strong> source of truth.
            </p>
          </div>
        </article>

        {result.errors.length > 0 ? (
          <article className="content-card content-col-12 notice-card notice-error">
            <h3>Blocking Issues</h3>
            <ul className="stack-list">
              {result.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </article>
        ) : null}

        {result.warnings.length > 0 ? (
          <article className="content-card content-col-12 notice-card notice-warning">
            <h3>Partial Data Warnings</h3>
            <ul className="stack-list">
              {result.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </article>
        ) : null}

        {result.snapshot ? (
          <>
            <article className="content-card content-col-8">
              <h3>Daily Brief</h3>
              <h4>{result.snapshot.headline}</h4>
              <p>{result.snapshot.briefSummary}</p>

              <div className="label-row">
                {result.snapshot.opportunity ? (
                  <span className="pill pill-opportunity">Opportunity: {result.snapshot.opportunity}</span>
                ) : null}
                {result.snapshot.warning ? (
                  <span className="pill pill-warning">Warning: {result.snapshot.warning}</span>
                ) : null}
              </div>

              <div className="source-grid">
                <div className="source-chip">
                  <strong>Brief endpoint:</strong> {result.snapshot.source.brief ? 'Live' : 'Missing'}
                </div>
                <div className="source-chip">
                  <strong>Day summary:</strong> {result.snapshot.source.daySummary ? 'Live' : 'Missing'}
                </div>
                <div className="source-chip">
                  <strong>Economy summary:</strong> {result.snapshot.source.economySummary ? 'Live' : 'Missing'}
                </div>
              </div>
            </article>

            <article className="content-card content-col-4">
              <h3>Player Snapshot</h3>
              <div className="metric-grid">
                <div className="metric">
                  <p className="metric-label">Cash</p>
                  <p className="metric-value">{formatXgp(result.snapshot.cashXgp)}</p>
                </div>
                <div className="metric">
                  <p className="metric-label">Debt</p>
                  <p className="metric-value strong-negative">{formatXgp(result.snapshot.debtXgp)}</p>
                </div>
                <div className="metric">
                  <p className="metric-label">Net Flow</p>
                  <p
                    className={`metric-value ${
                      (result.snapshot.netFlowXgp ?? 0) >= 0 ? 'strong-positive' : 'strong-negative'
                    }`}
                  >
                    {formatSignedXgp(result.snapshot.netFlowXgp)}
                  </p>
                </div>
              </div>
              <p>
                Day: {result.snapshot.dayNumber ?? 'N/A'} | As of: {result.snapshot.asOfDate ?? 'N/A'}
              </p>
            </article>

            <article className="content-card content-col-12">
              <h3>Portfolio (Optional)</h3>
              {result.snapshot.portfolio ? (
                <>
                  <div className="metric-grid">
                    <div className="metric">
                      <p className="metric-label">Available Cash</p>
                      <p className="metric-value">{formatXgp(result.snapshot.portfolio.availableCashXgp)}</p>
                    </div>
                    <div className="metric">
                      <p className="metric-label">Market Value</p>
                      <p className="metric-value">{formatXgp(result.snapshot.portfolio.marketValueXgp)}</p>
                    </div>
                    <div className="metric">
                      <p className="metric-label">Unrealized PnL</p>
                      <p
                        className={`metric-value ${
                          (result.snapshot.portfolio.unrealizedPnlXgp ?? 0) >= 0 ? 'strong-positive' : 'strong-negative'
                        }`}
                      >
                        {formatSignedXgp(result.snapshot.portfolio.unrealizedPnlXgp)}
                      </p>
                    </div>
                    <div className="metric">
                      <p className="metric-label">Holdings</p>
                      <p className="metric-value">{result.snapshot.portfolio.holdingsCount}</p>
                    </div>
                  </div>

                  <ul className="stack-list">
                    {result.snapshot.portfolio.topHoldings.length > 0 ? (
                      result.snapshot.portfolio.topHoldings.map((holding) => (
                        <li key={holding.ticker}>
                          {holding.ticker}: {holding.shares.toLocaleString()} shares ({formatXgp(holding.marketValueXgp)})
                        </li>
                      ))
                    ) : (
                      <li>No holdings are active for this player yet.</li>
                    )}
                  </ul>
                  <p>Latest market day: {result.snapshot.portfolio.latestMarketDay ?? 'N/A'}</p>
                </>
              ) : (
                <p>Portfolio data is currently unavailable for this player or environment.</p>
              )}
            </article>
          </>
        ) : (
          <article className="content-card content-col-12">
            <h3>No Snapshot Yet</h3>
            <p>Provide a valid player ID and backend URL to load the Gold Penny web companion data.</p>
          </article>
        )}

        <article className="content-card content-col-12">
          <h3>Mobile Continuation</h3>
          <p>Gameplay should continue in the app to keep runtime logic centralized.</p>
          <div className="button-row">
            <a href={deepLink} className="primary-button">
              Continue in App
            </a>
            <Link href="/connect" className="secondary-button">
              Open Wallet Prep
            </Link>
          </div>
        </article>
      </section>
    </BridgeShell>
  );
}

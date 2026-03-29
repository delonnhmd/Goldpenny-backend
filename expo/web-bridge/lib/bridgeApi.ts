import 'server-only';

import { resolveBackendBaseUrl, resolvePlayerId } from '@/lib/config';
import { asNumber, asText, firstMeaningfulLine, pickFirstString } from '@/lib/formatters';
import {
  BriefResponse,
  BridgeLoadResult,
  BridgePortfolioSnapshot,
  BridgeSnapshot,
  DaySummaryResponse,
  EconomyPresentationSummaryResponse,
  PlayerPortfolioResponse,
  StockQuotesResponse,
} from '@/lib/types';

interface LoadSnapshotOptions {
  playerIdOverride?: string | null;
  backendOverride?: string | null;
}

interface FetchCaptureSuccess<T> {
  ok: true;
  data: T;
}

interface FetchCaptureFailure {
  ok: false;
  error: string;
}

type FetchCapture<T> = FetchCaptureSuccess<T> | FetchCaptureFailure;

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

async function fetchBackendJson<T>(baseUrl: string, path: string): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    const text = await response.text();
    const snippet = text.slice(0, 160).replace(/\s+/g, ' ');
    throw new Error(`${path} failed (${response.status}). ${snippet}`.trim());
  }

  return (await response.json()) as T;
}

async function capture<T>(promise: Promise<T>): Promise<FetchCapture<T>> {
  try {
    return {
      ok: true,
      data: await promise,
    };
  } catch (error) {
    return {
      ok: false,
      error: toErrorMessage(error),
    };
  }
}

function firstBriefHint(brief: BriefResponse | null): string | null {
  if (!brief || !Array.isArray(brief.action_hints_json)) return null;

  for (const entry of brief.action_hints_json) {
    if (typeof entry === 'string' && entry.trim().length > 0) {
      return entry.trim().replace(/_/g, ' ');
    }

    if (entry && typeof entry === 'object') {
      const candidate = asText(entry.reason) ?? asText(entry.description) ?? asText(entry.title);
      if (candidate) return candidate;
    }
  }

  return null;
}

function normalizePortfolio(
  quotesResponse: StockQuotesResponse | null,
  portfolioResponse: PlayerPortfolioResponse | null,
): BridgePortfolioSnapshot | null {
  if (!portfolioResponse) return null;

  const holdingsRaw = Array.isArray(portfolioResponse.holdings) ? portfolioResponse.holdings : [];

  const topHoldings = holdingsRaw
    .map((holding) => ({
      ticker: asText(holding.ticker) ?? 'UNKNOWN',
      shares: asNumber(holding.shares) ?? 0,
      marketValueXgp: asNumber(holding.market_value) ?? 0,
    }))
    .filter((holding) => holding.shares > 0)
    .sort((left, right) => right.marketValueXgp - left.marketValueXgp)
    .slice(0, 3);

  const holdingsCount = holdingsRaw.filter((holding) => (asNumber(holding.shares) ?? 0) > 0).length;

  const latestMarketDay = (() => {
    if (!quotesResponse || !Array.isArray(quotesResponse.quotes)) return null;
    const values = quotesResponse.quotes
      .map((quote) => asNumber(quote.latest_day))
      .filter((value): value is number => value != null);
    if (values.length === 0) return null;
    return Math.max(...values);
  })();

  const snapshot: BridgePortfolioSnapshot = {
    latestMarketDay,
    availableCashXgp: asNumber(portfolioResponse.cash_xgp),
    marketValueXgp: asNumber(portfolioResponse.total_market_value),
    unrealizedPnlXgp: asNumber(portfolioResponse.total_unrealized_pnl),
    holdingsCount,
    topHoldings,
  };

  const hasAnyData =
    snapshot.availableCashXgp != null ||
    snapshot.marketValueXgp != null ||
    snapshot.unrealizedPnlXgp != null ||
    snapshot.holdingsCount > 0;

  return hasAnyData ? snapshot : null;
}

function buildSnapshot(options: {
  playerId: string;
  brief: BriefResponse | null;
  daySummary: DaySummaryResponse | null;
  economySummary: EconomyPresentationSummaryResponse | null;
  portfolio: BridgePortfolioSnapshot | null;
  source: BridgeSnapshot['source'];
}): BridgeSnapshot {
  const { playerId, brief, daySummary, economySummary, portfolio, source } = options;

  const economySummaryLines = economySummary?.daily_brief?.summary_lines;
  const summaryFromEconomy = pickFirstString(economySummaryLines);
  const summaryFromBrief = asText(brief?.summary);

  const briefSummary =
    firstMeaningfulLine(summaryFromEconomy ?? summaryFromBrief ?? null) ??
    'No Daily Brief is available yet. Continue gameplay in the mobile app for the latest update.';

  const netFlowFromDay = asNumber(daySummary?.net_change_xgp);
  const income = asNumber(daySummary?.income_xgp);
  const expenses = asNumber(daySummary?.expenses_xgp);
  const derivedNetFlow = netFlowFromDay ?? (income != null && expenses != null ? income - expenses : null);

  const netFlowFromEconomy = asNumber(economySummary?.settlement_summary?.net_change_xgp);

  return {
    playerId,
    dayNumber:
      asNumber(economySummary?.current_day) ??
      asNumber(daySummary?.day_number) ??
      asNumber(brief?.day),
    asOfDate: asText(economySummary?.as_of_date) ?? asText(daySummary?.created_at),
    headline:
      asText(economySummary?.daily_brief?.headline) ??
      asText(brief?.headline) ??
      'Today at Gold Penny',
    briefSummary,
    opportunity: pickFirstString(economySummary?.player_opportunities) ?? firstBriefHint(brief),
    warning: pickFirstString(economySummary?.player_warnings),
    cashXgp: asNumber(daySummary?.ending_cash_xgp),
    debtXgp: asNumber(daySummary?.ending_debt_xgp) ?? asNumber(daySummary?.debt_xgp),
    netFlowXgp: derivedNetFlow ?? netFlowFromEconomy,
    portfolio,
    source,
  };
}

export async function loadBridgeSnapshot(options: LoadSnapshotOptions): Promise<BridgeLoadResult> {
  const playerId = resolvePlayerId(options.playerIdOverride);
  const backendBaseUrl = resolveBackendBaseUrl(options.backendOverride);

  const errors: string[] = [];
  const warnings: string[] = [];

  if (!playerId) {
    errors.push('Player ID is required. Pass ?playerId=<uuid> or set GOLDPENNY_DEFAULT_PLAYER_ID.');
  }

  if (!backendBaseUrl) {
    errors.push('Backend URL is required. Set GOLDPENNY_BACKEND_URL or pass ?backend=https://api-host.');
  }

  if (!playerId || !backendBaseUrl) {
    return {
      backendBaseUrl,
      playerId,
      snapshot: null,
      errors,
      warnings,
    };
  }

  const encodedPlayerId = encodeURIComponent(playerId);

  const [briefResult, daySummaryResult, economySummaryResult, quotesResult, portfolioResult] = await Promise.all([
    capture(fetchBackendJson<BriefResponse>(backendBaseUrl, `/briefs/player/${encodedPlayerId}/latest`)),
    capture(fetchBackendJson<DaySummaryResponse>(backendBaseUrl, `/day/summary/${encodedPlayerId}`)),
    capture(
      fetchBackendJson<EconomyPresentationSummaryResponse>(
        backendBaseUrl,
        `/economy-presentation/player/${encodedPlayerId}/summary`,
      ),
    ),
    capture(fetchBackendJson<StockQuotesResponse>(backendBaseUrl, '/stocks/quotes')),
    capture(fetchBackendJson<PlayerPortfolioResponse>(backendBaseUrl, `/stocks/portfolio/${encodedPlayerId}`)),
  ]);

  if (!briefResult.ok) warnings.push(`Daily Brief unavailable: ${briefResult.error}`);
  if (!daySummaryResult.ok) warnings.push(`Player summary unavailable: ${daySummaryResult.error}`);
  if (!economySummaryResult.ok) warnings.push(`Economy summary unavailable: ${economySummaryResult.error}`);
  if (!quotesResult.ok) warnings.push(`Stock quotes unavailable: ${quotesResult.error}`);
  if (!portfolioResult.ok) warnings.push(`Portfolio unavailable: ${portfolioResult.error}`);

  const hasCoreData = briefResult.ok || daySummaryResult.ok || economySummaryResult.ok;

  if (!hasCoreData) {
    errors.push('No core gameplay data could be loaded from backend endpoints.');
    return {
      backendBaseUrl,
      playerId,
      snapshot: null,
      errors,
      warnings,
    };
  }

  const snapshot = buildSnapshot({
    playerId,
    brief: briefResult.ok ? briefResult.data : null,
    daySummary: daySummaryResult.ok ? daySummaryResult.data : null,
    economySummary: economySummaryResult.ok ? economySummaryResult.data : null,
    portfolio: normalizePortfolio(quotesResult.ok ? quotesResult.data : null, portfolioResult.ok ? portfolioResult.data : null),
    source: {
      brief: briefResult.ok,
      daySummary: daySummaryResult.ok,
      economySummary: economySummaryResult.ok,
      portfolio: portfolioResult.ok,
    },
  });

  return {
    backendBaseUrl,
    playerId,
    snapshot,
    errors,
    warnings,
  };
}
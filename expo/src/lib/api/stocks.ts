import { fetchApiWithFallback } from '@/lib/apiClient';
import { normalizeCurrentDay, normalizeFiniteNumber, normalizeMoneyValue } from '@/lib/economySafety';
import {
  StockMarketSnapshotResponse,
  StockTradeExecutionResponse,
  StockVolatilityLabel,
} from '@/types/stocks';

interface RawQuote {
  ticker?: unknown;
  latest_day?: unknown;
  sector?: unknown;
  close_price?: unknown;
  daily_change_pct?: unknown;
}

interface RawHolding {
  ticker?: unknown;
  shares?: unknown;
  average_cost_basis?: unknown;
  latest_price?: unknown;
  market_value?: unknown;
  unrealized_pnl?: unknown;
}

function toStringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function previousCloseFromChange(currentPrice: number, dailyChangePct: number): number {
  const ratio = 1 + (dailyChangePct / 100);
  if (!Number.isFinite(ratio) || Math.abs(ratio) < 0.000001) return currentPrice;
  return normalizeMoneyValue(currentPrice / ratio, { allowNegative: false, fallback: currentPrice });
}

function toVolatilityLabel(dailyChangePct: number): StockVolatilityLabel {
  const absChange = Math.abs(normalizeFiniteNumber(dailyChangePct, { fallback: 0 }));
  if (absChange >= 3) return 'hot';
  if (absChange >= 1.25) return 'active';
  return 'steady';
}

const STOCK_METADATA: Record<string, { stockName: string; sectorKey: string }> = {
  GPEN: { stockName: 'GP Energy', sectorKey: 'energy' },
  GPTECH: { stockName: 'GP Tech', sectorKey: 'technology' },
  GPRETAIL: { stockName: 'GP Retail', sectorKey: 'retail' },
  GPHEALTH: { stockName: 'GP Health', sectorKey: 'healthcare' },
  GPBANK: { stockName: 'GP Bank', sectorKey: 'finance' },
  GPAUTO: { stockName: 'GP Auto', sectorKey: 'automotive' },
  GPTRANS: { stockName: 'GP Transport', sectorKey: 'transport' },
  GPREAL: { stockName: 'GP Real Estate', sectorKey: 'real_estate' },
  GPDEF: { stockName: 'GP Defense', sectorKey: 'defense' },
  GPCONS: { stockName: 'GP Consumer', sectorKey: 'consumer' },
};

function buildSectorSignalSummary(sectorKey: string, dailyChangePct: number): string {
  const move = normalizeFiniteNumber(dailyChangePct, { fallback: 0 });
  const sectorLabel = String(sectorKey || 'market').replace(/_/g, ' ');
  if (move >= 1) return `${sectorLabel} closed strong after the backend daily macro update.`;
  if (move <= -1) return `${sectorLabel} closed weak after the backend daily macro update.`;
  return `${sectorLabel} held near flat on the canonical daily close.`;
}

export async function getStockMarketSnapshot(playerId: string): Promise<StockMarketSnapshotResponse> {
  const [quotesRaw, portfolioRaw] = await Promise.all([
    fetchApiWithFallback<Record<string, unknown>>(['/stocks/quotes']),
    fetchApiWithFallback<Record<string, unknown>>([`/stocks/portfolio/${playerId}`]),
  ]);

  const quotes = Array.isArray(quotesRaw.quotes) ? (quotesRaw.quotes as RawQuote[]) : [];
  const holdings = Array.isArray(portfolioRaw.holdings) ? (portfolioRaw.holdings as RawHolding[]) : [];

  const holdingByTicker = new Map(holdings.map((holding) => [toStringValue(holding.ticker).toUpperCase(), holding]));

  const stocks = quotes.map((quote) => {
    const stockId = toStringValue(quote.ticker).toUpperCase();
    const holding = holdingByTicker.get(stockId);
    const currentPrice = normalizeMoneyValue(quote.close_price, { allowNegative: false, fallback: 0 });
    const dailyChangePct = normalizeFiniteNumber(quote.daily_change_pct, { fallback: 0, min: -100, max: 100 });
    const previousClose = previousCloseFromChange(currentPrice, dailyChangePct);
    const quantity = normalizeFiniteNumber(holding?.shares, { fallback: 0, min: 0, round: 'floor' });
    const avgCost = normalizeMoneyValue(holding?.average_cost_basis, { allowNegative: false, fallback: 0 });
    const marketValue = normalizeMoneyValue(holding?.market_value, { allowNegative: false, fallback: currentPrice * quantity });
    const unrealized = normalizeMoneyValue(holding?.unrealized_pnl, { allowNegative: true, fallback: marketValue - (avgCost * quantity) });
    const latestDay = normalizeCurrentDay(quote.latest_day, 1);
    const metadata = STOCK_METADATA[stockId];
    const sectorKey = toStringValue(quote.sector, metadata?.sectorKey || 'unknown');

    return {
      stock_id: stockId,
      stock_name: metadata?.stockName || stockId,
      sector_key: sectorKey,
      current_price: currentPrice,
      previous_close: previousClose,
      daily_change_pct: dailyChangePct,
      latest_day: latestDay,
      sector_signal_summary: buildSectorSignalSummary(sectorKey, dailyChangePct),
      volatility_label: toVolatilityLabel(dailyChangePct),
      can_trade: currentPrice > 0,
      holdings_quantity: quantity,
      holdings_cost_basis: avgCost,
      holdings_market_value: marketValue,
      holdings_unrealized_pnl: unrealized,
    };
  });

  const latestDay = stocks.reduce<number | null>((maxDay, stock) => {
    if (maxDay == null) return stock.latest_day;
    return Math.max(maxDay, stock.latest_day);
  }, null);

  const totalMarketValue = normalizeMoneyValue(portfolioRaw.total_market_value, { allowNegative: false, fallback: 0 });
  const totalCostBasis = normalizeMoneyValue(portfolioRaw.total_cost_basis, { allowNegative: false, fallback: 0 });
  const totalUnrealized = normalizeMoneyValue(portfolioRaw.total_unrealized_pnl, { allowNegative: true, fallback: totalMarketValue - totalCostBasis });
  const availableCash = normalizeMoneyValue(portfolioRaw.cash_xgp, { allowNegative: true, fallback: 0 });

  return {
    player_id: playerId,
    latest_day: latestDay,
    stocks,
    portfolio: {
      available_cash_xgp: availableCash,
      total_market_value_xgp: totalMarketValue,
      total_cost_basis_xgp: totalCostBasis,
      total_unrealized_pnl_xgp: totalUnrealized,
      total_portfolio_value_xgp: normalizeMoneyValue(availableCash + totalMarketValue, { allowNegative: true, fallback: availableCash }),
      holdings_count: stocks.filter((stock) => stock.holdings_quantity > 0).length,
    },
  };
}

export async function buyStock(playerId: string, stockId: string, shares = 1): Promise<StockTradeExecutionResponse> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>(['/stocks/buy'], {
    method: 'POST',
    body: JSON.stringify({ player_id: playerId, ticker: stockId, shares }),
  });

  return {
    player_id: playerId,
    stock_id: toStringValue(raw.ticker, stockId).toUpperCase(),
    trade_type: 'buy',
    shares: normalizeFiniteNumber(raw.shares_bought ?? shares, { fallback: shares, min: 1, round: 'floor' }),
    execution_price: normalizeMoneyValue(raw.execution_price, { allowNegative: false, fallback: 0 }),
    gross_amount: normalizeMoneyValue(raw.gross_amount, { allowNegative: false, fallback: 0 }),
    fee_amount: normalizeMoneyValue(raw.fee_amount, { allowNegative: false, fallback: 0 }),
    net_amount: normalizeMoneyValue(raw.total_cost, { allowNegative: false, fallback: 0 }),
    remaining_cash_xgp: normalizeMoneyValue(raw.remaining_cash, { allowNegative: true, fallback: 0 }),
    remaining_holding_shares: normalizeFiniteNumber(raw.updated_holding_shares, { fallback: 0, min: 0, round: 'floor' }),
  };
}

export async function sellStock(playerId: string, stockId: string, shares = 1): Promise<StockTradeExecutionResponse> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>(['/stocks/sell'], {
    method: 'POST',
    body: JSON.stringify({ player_id: playerId, ticker: stockId, shares }),
  });

  return {
    player_id: playerId,
    stock_id: toStringValue(raw.ticker, stockId).toUpperCase(),
    trade_type: 'sell',
    shares: normalizeFiniteNumber(raw.shares_sold ?? shares, { fallback: shares, min: 1, round: 'floor' }),
    execution_price: normalizeMoneyValue(raw.execution_price, { allowNegative: false, fallback: 0 }),
    gross_amount: normalizeMoneyValue(raw.gross_amount, { allowNegative: false, fallback: 0 }),
    fee_amount: normalizeMoneyValue(raw.fee_amount, { allowNegative: false, fallback: 0 }),
    net_amount: normalizeMoneyValue(raw.net_amount, { allowNegative: false, fallback: 0 }),
    remaining_cash_xgp: normalizeMoneyValue(raw.remaining_cash, { allowNegative: true, fallback: 0 }),
    remaining_holding_shares: normalizeFiniteNumber(raw.remaining_holding_shares, { fallback: 0, min: 0, round: 'floor' }),
    realized_pnl_xgp: normalizeMoneyValue(raw.realized_pnl, { allowNegative: true, fallback: 0 }),
  };
}

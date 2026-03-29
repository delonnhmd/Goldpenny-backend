export interface BriefActionHint {
  action_key?: string;
  title?: string;
  reason?: string;
  description?: string;
}

export interface BriefResponse {
  player_id?: string;
  day?: number;
  headline?: string;
  summary?: string;
  action_hints_json?: Array<string | BriefActionHint>;
}

export interface DaySummaryResponse {
  player_id?: string;
  day_number?: number;
  ending_cash_xgp?: number;
  ending_debt_xgp?: number;
  debt_xgp?: number;
  income_xgp?: number;
  expenses_xgp?: number;
  net_change_xgp?: number;
  created_at?: string;
}

export interface EconomyDailyBriefResponse {
  day?: number;
  headline?: string;
  summary_lines?: string[];
}

export interface EconomySettlementSummary {
  net_change_xgp?: number;
}

export interface EconomyPresentationSummaryResponse {
  as_of_date?: string;
  current_day?: number;
  player_opportunities?: string[];
  player_warnings?: string[];
  daily_brief?: EconomyDailyBriefResponse;
  settlement_summary?: EconomySettlementSummary;
}

export interface StockQuote {
  latest_day?: number;
}

export interface StockQuotesResponse {
  count?: number;
  quotes?: StockQuote[];
}

export interface StockHolding {
  ticker?: string;
  shares?: number;
  market_value?: number;
  unrealized_pnl?: number;
}

export interface PlayerPortfolioResponse {
  cash_xgp?: number;
  total_market_value?: number;
  total_unrealized_pnl?: number;
  holdings?: StockHolding[];
}

export interface BridgePortfolioSnapshot {
  latestMarketDay: number | null;
  availableCashXgp: number | null;
  marketValueXgp: number | null;
  unrealizedPnlXgp: number | null;
  holdingsCount: number;
  topHoldings: Array<{
    ticker: string;
    shares: number;
    marketValueXgp: number;
  }>;
}

export interface BridgeSnapshot {
  playerId: string;
  dayNumber: number | null;
  asOfDate: string | null;
  headline: string;
  briefSummary: string;
  opportunity: string | null;
  warning: string | null;
  cashXgp: number | null;
  debtXgp: number | null;
  netFlowXgp: number | null;
  portfolio: BridgePortfolioSnapshot | null;
  source: {
    brief: boolean;
    daySummary: boolean;
    economySummary: boolean;
    portfolio: boolean;
  };
}

export interface BridgeLoadResult {
  backendBaseUrl: string | null;
  playerId: string | null;
  snapshot: BridgeSnapshot | null;
  errors: string[];
  warnings: string[];
}
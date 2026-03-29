export type StockTradeSide = 'buy' | 'sell';
export type StockVolatilityLabel = 'steady' | 'active' | 'hot';

export interface StockHoldingSummary {
  stock_id: string;
  holdings_quantity: number;
  holdings_cost_basis: number;
  holdings_market_value: number;
  holdings_unrealized_pnl: number;
}

export interface StockMarketItem extends StockHoldingSummary {
  stock_id: string;
  stock_name: string;
  sector_key: string;
  current_price: number;
  previous_close: number;
  daily_change_pct: number;
  latest_day: number;
  sector_signal_summary: string;
  volatility_label: StockVolatilityLabel;
  can_trade: boolean;
}

export interface StockPortfolioSummary {
  available_cash_xgp: number;
  total_market_value_xgp: number;
  total_cost_basis_xgp: number;
  total_unrealized_pnl_xgp: number;
  total_portfolio_value_xgp: number;
  holdings_count: number;
}

export interface StockMarketSnapshotResponse {
  player_id: string;
  latest_day: number | null;
  stocks: StockMarketItem[];
  portfolio: StockPortfolioSummary;
}

export interface StockTradeExecutionResponse {
  player_id: string;
  stock_id: string;
  trade_type: StockTradeSide;
  shares: number;
  execution_price: number;
  gross_amount: number;
  fee_amount: number;
  net_amount: number;
  remaining_cash_xgp: number;
  remaining_holding_shares: number;
  realized_pnl_xgp?: number;
}

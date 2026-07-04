export type PaperTradeStatus = "OPEN" | "CLOSED" | "EXPIRED";

export interface PaperTrade {
  id: string;
  created_date: string;
  symbol: string;
  underlying_price_at_entry: number;
  strategy_type: string;
  expiry_date: string;
  days_to_entry_dte: number;
  long_strike: number;
  short_strike: number;
  long_option_type: string;
  short_option_type: string;
  entry_debit: number | null;
  entry_credit: number | null;
  quantity: number;
  max_profit: number;
  max_loss: number;
  breakeven: number;
  entry_delta_long?: number | null;
  entry_delta_short?: number | null;
  entry_iv?: number | null;
  entry_atr?: number | null;
  entry_rsi?: number | null;
  entry_macd?: number | null;
  market_bias?: string | null;
  confidence?: string | null;
  reason_for_trade?: string | null;
  notes?: string | null;
  status: PaperTradeStatus;
  exit_date?: string | null;
  exit_reason?: string | null;
  current_underlying_price?: number | null;
  current_spread_value?: number | null;
  realized_pnl?: number | null;
  unrealized_pnl?: number | null;
  percent_return?: number | null;
  highest_profit_seen?: number | null;
  largest_drawdown?: number | null;
  last_marked_at?: string | null;
  execution_enabled?: boolean;
  source?: string | null;
  ibkr_sync_key?: string | null;
  long_con_id?: number | null;
  short_con_id?: number | null;
  average_cost?: number | null;
  market_value?: number | null;
  today_pnl?: number | null;
  long_bid?: number | null;
  long_ask?: number | null;
  long_mid?: number | null;
  short_bid?: number | null;
  short_ask?: number | null;
  short_mid?: number | null;
  max_profit_remaining?: number | null;
  progress_pct?: number | null;
  breakeven_distance?: number | null;
  distance_to_long_strike?: number | null;
  distance_to_short_strike?: number | null;
}

export interface PaperTradeSnapshot {
  id: string;
  trade_id: string;
  marked_at: string;
  underlying_price?: number | null;
  spread_value?: number | null;
  unrealized_pnl?: number | null;
  percent_return?: number | null;
  snapshot_json?: Record<string, unknown> | null;
}

export interface PaperTradeReview {
  id: string;
  trade_id: string;
  created_at: string;
  what_went_right?: string | null;
  what_went_wrong?: string | null;
  indicators_agreed?: string | null;
  regime_change?: string | null;
  would_recommend_again?: string | null;
}

export interface PaperTradeDetail extends PaperTrade {
  snapshots: PaperTradeSnapshot[];
  review?: PaperTradeReview | null;
  entry_snapshot_json?: Record<string, unknown> | null;
}

export interface PaperTradeSummary {
  open_count: number;
  closed_count: number;
  total_trades: number;
  win_rate: number;
  avg_return_pct: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  best_trade_pnl: number;
  worst_trade_pnl: number;
  avg_holding_days: number;
}

export interface PaperTradeAnalytics {
  strategy_breakdown: Array<{
    strategy_type: string;
    count: number;
    win_rate: number;
    total_pnl: number;
  }>;
  monthly_returns: Array<{ month: string; pnl: number }>;
  profit_factor: number;
  gross_profit: number;
  gross_loss: number;
}

export interface PaperTradeSyncStatus {
  gateway: { available: boolean; backend?: string; message: string };
  broker?: { available: boolean; backend?: string; message: string };
  last_sync: {
    synced_at: string;
    action: string;
    records_updated: number;
    new_trades: number;
    closed_trades: number;
    failed_requests: number;
    message?: string | null;
  } | null;
}

export interface IbkrSyncResult {
  action: string;
  records_updated: number;
  new_trades: number;
  closed_trades: number;
  failed_requests: number;
  spreads_matched?: number;
  gateway_available?: boolean;
  message?: string;
}

export interface PaperTradeFilters {
  symbol?: string;
  strategy_type?: string;
  status?: PaperTradeStatus;
  profit_only?: boolean;
  loss_only?: boolean;
}

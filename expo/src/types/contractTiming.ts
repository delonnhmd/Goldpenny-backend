// Step 41: Contract Timing — TypeScript type definitions.
// Auto-generated from app/schemas/contract_timing.py

export interface DueSoonItem {
  key: string;
  type: string;
  family: string;
  amount_xgp: number;
  due_on_day: number;
  days_away: number;
  income_flag: boolean;
  status: string;
}

export interface PlayerContractScheduleResponse {
  player_id: string;
  day: number;
  active_contract_count: number;
  total_due_7d_xgp: number;
  clustering_label: string;
  next_major_due_on: number | null;
  next_major_due_type: string | null;
  days_to_next_major_due: number | null;
  next_income_on: number | null;
  next_income_type: string | null;
  days_to_next_income: number | null;
  contract_density_score: number;
  timing_stability_score: number;
  cash_gap_before_next_income_xgp: number;
  timing_pressure_label: string;
  bridge_need_label: string;
  obligation_collision_label: string;
  false_payday_pressure: boolean;
  recurring_obligation_map: Record<string, unknown>;
  income_cadence: Record<string, unknown>;
  due_window: Record<string, unknown>;
}

export interface UpcomingObligationWindowResponse {
  player_id: string;
  day: number;
  due_today: Record<string, unknown>[];
  due_in_3d: Record<string, unknown>[];
  due_in_7d: Record<string, unknown>[];
  outflows_due_today_xgp: number;
  outflows_due_3d_xgp: number;
  outflows_due_7d_xgp: number;
  inflows_expected_7d_xgp: number;
  net_7d_xgp: number;
}

export interface CashTimingPressureStateResponse {
  player_id: string;
  day: number;
  cash_on_hand_xgp: number;
  cash_gap_before_next_income_xgp: number;
  contract_density_score: number;
  timing_stability_score: number;
  timing_pressure_label: string;
  clustering_label: string;
  bridge_need_label: string;
  obligation_collision_label: string;
  false_payday_pressure: boolean;
  next_income_on: number | null;
  next_income_type: string | null;
  days_to_next_income: number | null;
  next_major_due_on: number | null;
  next_major_due_type: string | null;
  days_to_next_major_due: number | null;
}

export interface DueSoonSummaryResponse {
  player_id: string;
  day: number;
  cash_on_hand_xgp: number;
  total_due_7d_xgp: number;
  total_income_expected_7d_xgp: number;
  projected_net_xgp: number;
  item_count: number;
  items: DueSoonItem[];
}

export interface ContractPressureSummaryResponse {
  player_id: string;
  day: number;
  // timing pressure
  timing_pressure_label: string;
  clustering_label: string;
  bridge_need_label: string;
  obligation_collision_label: string;
  contract_density_score: number;
  timing_stability_score: number;
  false_payday_pressure: boolean;
  // cash position
  cash_on_hand_xgp: number;
  cash_gap_before_next_income_xgp: number;
  // upcoming window
  outflows_due_today_xgp: number;
  outflows_due_3d_xgp: number;
  outflows_due_7d_xgp: number;
  inflows_expected_7d_xgp: number;
  net_7d_xgp: number;
  // income timing
  next_income_on: number | null;
  next_income_type: string | null;
  days_to_next_income: number | null;
  // next major obligation
  next_major_due_on: number | null;
  next_major_due_type: string | null;
  days_to_next_major_due: number | null;
  // risk signals
  late_event_count: number;
  delinquency_stage: string;
  bridge_borrow_is_rational: boolean;
  due_soon_items: DueSoonItem[];
}

// Label union types for type-safe comparisons
export type TimingPressureLabel = 'low' | 'manageable' | 'elevated' | 'severe';
export type ClusteringLabel = 'spread' | 'mild_cluster' | 'clustered' | 'heavily_clustered';
export type BridgeNeedLabel = 'none' | 'pre_payday_squeeze' | 'moderate' | 'urgent';
export type ObligationCollisionLabel = 'none' | 'overlap' | 'collision' | 'compound';
export type ContractEventStatus = 'upcoming' | 'due' | 'paid' | 'late' | 'rolled_forward' | 'waived';
export type ObligationFamily = 'personal' | 'debt' | 'business' | 'income';

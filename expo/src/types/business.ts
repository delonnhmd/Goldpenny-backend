// Gold Penny — canonical business path types for Fruit Shop and Food Truck.
// Source of truth: backend Step 15 player-id routes (/business/player/{player_id}).

export type BusinessTypeKey = 'fruit_shop' | 'food_truck';

export interface PlayerBusinessRecord {
  business_id: string;
  player_id: string;
  business_type: BusinessTypeKey | string;
  business_name: string | null;
  is_active: boolean;
  region_key: string | null;
  level: string | null;
  reputation: number;
  cash_invested_xgp: number;
  inventory_produce_units: number;
  inventory_essentials_units: number;
  inventory_protein_units: number;
  operating_mode: string | null;
  last_operated_on: string | null;
}

export interface BusinessProfitSnapshot {
  player_id?: string;
  day?: number;
  total_businesses?: number;
  active_businesses?: number;
  latest_daily_profit_xgp?: number;
  trailing_7d_profit_xgp?: number;
  inventory_estimated_value_xgp?: number;
  business_estimated_value_xgp?: number;
  business_type_breakdown?: {
    business_type: string;
    count: number;
    active_count: number;
    inventory_value_xgp: number;
    latest_daily_profit_xgp: number;
  }[];
}

export interface PlayerBusinessesResponse {
  player_id: string;
  businesses: PlayerBusinessRecord[];
  profit_snapshot: BusinessProfitSnapshot;
}

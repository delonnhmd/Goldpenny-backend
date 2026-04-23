// Gold Penny — canonical business path types for Fruit Shop and Food Truck.
// Source of truth: backend Step 15 player-id routes (/business/player/{player_id}).

export type BusinessTypeKey = 'fruit_shop' | 'food_truck';

export type BusinessFamilyKey = 'fruit' | 'food';

export type BusinessGrowthPhaseKey =
  | 'fruit_cart'
  | 'fruit_truck'
  | 'small_fruit_shop'
  | 'large_fruit_store'
  | 'fruit_chain'
  | 'fruit_corporation'
  | 'food_cart'
  | 'food_truck'
  | 'food_kiosk'
  | 'food_restaurant'
  | 'food_franchise'
  | 'food_corporation';

export type BusinessLandZoneType =
  | 'residential_edge'
  | 'mixed_use'
  | 'commercial_core'
  | 'service_flex'
  | 'logistics';

export type BusinessLotSize = 'micro' | 'small' | 'medium' | 'large';

export interface BusinessInventoryItem {
  item_id: string;
  display_name: string;
  basket_link: string;
  quantity: number;
  avg_unit_cost: number;
  retail_price: number;
  suggested_retail_price?: number;
  spoilage_rate: number;
  demand_weight: number;
  unit_label: string;
  economy_sensitivity: number;
  estimated_value_xgp?: number;
  estimated_days_of_stock_left?: number | null;
}

export interface BusinessDailyOperationRecord {
  business_id: string;
  business_type: BusinessTypeKey | string;
  as_of_date: string | null;
  day: number;
  region_key: string | null;
  gross_revenue_xgp: number;
  revenue_xgp: number;
  cost_of_goods_sold_xgp: number;
  cogs_xgp: number;
  labor_cost_xgp: number;
  overhead_xgp: number;
  spoilage_loss_xgp: number;
  fuel_cost_xgp: number;
  maintenance_cost_xgp: number;
  net_profit_xgp: number;
  units_sold: number;
  inventory_before: number;
  inventory_after: number;
  demand_signal: number;
  reputation_before: number;
  reputation_after: number;
  operating_mode?: string | null;
  upgrades?: string[];
  units_sold_by_item?: Record<string, number>;
  remaining_inventory_by_item?: Record<string, number>;
  remaining_inventory_value_xgp?: number;
  estimated_days_of_stock_left?: number | null;
  restock_warning?: string | null;
  lost_sales_units?: number;
  status?: string;
  message?: string;
}

export interface SupplierItemRecord {
  item_id: string;
  display_name: string;
  compatible_business_types: string[];
  basket_link: string;
  base_wholesale_cost: number;
  current_wholesale_cost: number;
  suggested_retail_price: number;
  current_retail_price: number;
  spoilage_rate: number;
  demand_weight: number;
  unit_label: string;
  economy_sensitivity: number;
}

export interface SupplierItemsResponse {
  business_type: BusinessTypeKey | string;
  day: number;
  as_of_date: string;
  count: number;
  items: SupplierItemRecord[];
}

export interface SupplierInventoryPurchaseResponse {
  player_id: string;
  business_id: string;
  business_type: BusinessTypeKey | string;
  day: number;
  as_of_date: string;
  cash_before_xgp: number;
  cash_after_xgp: number;
  total_purchase_cost_xgp: number;
  purchased_items: {
    item_id: string;
    quantity: number;
    unit_cost_xgp: number;
    retail_price_xgp: number;
    total_cost_xgp: number;
  }[];
  inventory_items: BusinessInventoryItem[];
  inventory_total_units: number;
  inventory_estimated_value_xgp: number;
  estimated_days_of_stock_left?: number | null;
  restock_warning?: string | null;
}

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
  startup_cost_xgp?: number;
  inventory_produce_units: number;
  inventory_essentials_units: number;
  inventory_protein_units: number;
  inventory_total_units?: number;
  inventory_estimated_value_xgp?: number;
  inventory_items?: BusinessInventoryItem[];
  estimated_days_of_stock_left?: number | null;
  restock_warning?: string | null;
  uses_itemized_inventory?: boolean;
  operating_mode: string | null;
  upgrades?: string[];
  last_operated_day?: number | null;
  last_operated_on: string | null;
  average_last_7_day_profit_xgp?: number;
  business_estimated_value_xgp?: number;
  latest_daily_log?: BusinessDailyOperationRecord | null;
  created_at?: string | null;
  updated_at?: string | null;
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
    business_value_xgp?: number;
    average_last_7_day_profit_xgp?: number;
    latest_daily_profit_xgp: number;
  }[];
}

export interface PlayerBusinessesResponse {
  player_id: string;
  businesses: PlayerBusinessRecord[];
  profit_snapshot: BusinessProfitSnapshot;
  starter_options?: {
    business_type: BusinessTypeKey | string;
    label: string;
    cost_xgp: number;
  }[];
}

export interface BusinessGrowthPhaseDefinition {
  key: BusinessGrowthPhaseKey;
  family: BusinessFamilyKey;
  label: string;
  stage: number;
  revenueBand: string;
  costBand: string;
  riskBand: string;
  staffCapacity: number;
  wageBaseXgp: number;
  managementTools: string[];
  unlockHint: string;
}

export interface BusinessMarketListing {
  listing_id: string;
  business_type: BusinessTypeKey | string;
  business_family: BusinessFamilyKey;
  listing_name: string;
  price_xgp: number;
  location_label: string;
  district_key: string | null;
  district_label: string | null;
  tile_key: string | null;
  tile_x: number | null;
  tile_y: number | null;
  growth_phase_key: BusinessGrowthPhaseKey;
  growth_phase_label: string;
  employees: number;
  employee_capacity: number;
  open_slots: number;
  wage_cost_xgp: number;
  performance_score: number;
  demand_score: number;
  reputation_score: number;
  traffic_potential: number;
  locked: boolean;
  lock_reason: string | null;
  management_tools: string[];
  buyable: boolean;
  compare_note: string;
}

export interface ActiveBusinessProfile {
  business_id: string;
  business_type: BusinessTypeKey | string;
  business_family: BusinessFamilyKey;
  display_name: string;
  growth_phase_key: BusinessGrowthPhaseKey;
  growth_phase_label: string;
  next_phase_key: BusinessGrowthPhaseKey | null;
  next_phase_label: string | null;
  employees: number;
  npc_employees: number;
  player_employees: number;
  employee_capacity: number;
  open_slots: number;
  wage_cost_xgp: number;
  performance_score: number;
  demand_score: number;
  reputation_score: number;
  traffic_score: number;
  risk_band: string;
  management_tools: string[];
  location_label: string;
  district_key: string | null;
  district_label: string | null;
  tile_key: string | null;
  phase_progress_label: string;
}

export interface SandboxOwnedLot {
  tile_key: string;
  x: number;
  y: number;
  address: string;
  district_key: string | null;
  district_label: string | null;
  region: string | null;
  zone_type: BusinessLandZoneType;
  size: BusinessLotSize;
  value_xgp: number;
  purchase_price_xgp: number;
  traffic_score: number;
  development_potential: number;
  demand_score: number;
  owner_player_id: string;
  planned_business_type: string | null;
  linked_business_id: string | null;
  placed_business_id: string | null;
  development_stage: 'land' | 'planned' | 'built';
  purchased_at: string;
}

export interface BusinessSandboxState {
  version: number;
  player_id: string;
  owned_lots: SandboxOwnedLot[];
  business_market_links: {
    business_id: string;
    listing_id: string;
    listing_name: string;
    tile_key: string | null;
    district_key: string | null;
    district_label: string | null;
    location_label: string;
    growth_phase_key: BusinessGrowthPhaseKey;
  }[];
}

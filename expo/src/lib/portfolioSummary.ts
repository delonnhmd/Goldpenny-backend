import {
  createSlotEconomicRecord,
  getStableSlotAddress,
} from './slotEconomics.ts';

export interface PortfolioOwnedLand {
  slot_id: string;
  address: string;
  region: string | null;
  district: string | null;
  slot_type: string | null;
  purchase_price: number;
  current_value: number;
  demand_score: number;
  foot_traffic_score: number;
  competition_score: number;
  risk_score: number;
  supply_access_score: number;
  best_business_fit: 'fruit_shop' | 'food_truck' | 'either' | null;
  linked_business_id: string | null;
  linked_business_type: string | null;
  ownership_status: string;
}

export interface PortfolioBusinessSummary {
  business_id: string;
  business_type: string;
  region: string | null;
  linked_slot_id: string | null;
  address: string | null;
  reputation: number;
  inventory_value: number;
  avg_7_day_profit: number;
  estimated_business_value: number;
  last_net_profit: number;
  last_operated_day: number | null;
}

export interface PortfolioSummary {
  player_id: string;
  day: number;
  cash: number;
  debt: number;
  stock_holdings_value: number;
  land_value: number;
  business_value: number;
  inventory_value: number;
  total_assets: number;
  net_worth: number;
  total_assets_without_sandbox_land: number;
  net_worth_without_sandbox_land: number;
  latest_business_profit: number;
  trailing_7d_business_profit: number;
  active_business_count: number;
  owned_land: PortfolioOwnedLand[];
  businesses: PortfolioBusinessSummary[];
}

export interface SandboxPortfolioLot {
  tile_key: string;
  address?: string | null;
  district_key?: string | null;
  district_label?: string | null;
  region?: string | null;
  zone_type?: string | null;
  purchase_price_xgp?: number | null;
  value_xgp?: number | null;
  demand_score?: number | null;
  foot_traffic_score?: number | null;
  traffic_score?: number | null;
  competition_score?: number | null;
  risk_score?: number | null;
  supply_access_score?: number | null;
  best_business_fit?: 'fruit_shop' | 'food_truck' | 'either' | null;
  linked_business_id?: string | null;
  linked_business_type?: string | null;
  placed_business_id?: string | null;
  planned_business_type?: string | null;
  development_potential?: number | null;
  location_business_multiplier?: number | null;
  development_stage?: string | null;
  ownership_status?: string | null;
}

function normalizeMoney(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.round(parsed * 100) / 100;
}

function normalizeFinite(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function buildDeterministicPortfolioAddress(slotId: string, district: string | null | undefined): string {
  return getStableSlotAddress({
    slot_id: slotId,
    district,
    region: district,
  });
}

export function estimatePortfolioLandCurrentValue(
  purchasePrice: number,
  demandScore: number,
  district: string | null | undefined,
): number {
  return createSlotEconomicRecord({
    slot_id: `portfolio-preview:${district || 'unknown'}:${purchasePrice}:${demandScore}`,
    district,
    region: district,
    purchase_price: purchasePrice,
    demand_score: demandScore,
    foot_traffic_score: demandScore,
    risk_score: demandScore >= 50 ? 0 : 100,
  }).current_value;
}

function normalizeSummaryLand(land: PortfolioOwnedLand): PortfolioOwnedLand {
  const economicSlot = createSlotEconomicRecord({
    slot_id: land.slot_id,
    address: land.address,
    region: land.region,
    district: land.district,
    slot_type: land.slot_type,
    purchase_price: normalizeMoney(land.purchase_price, 0),
    current_value: land.current_value,
    demand_score: normalizeFinite(land.demand_score, 0),
    foot_traffic_score: normalizeFinite(land.foot_traffic_score, land.demand_score),
    traffic_score: normalizeFinite(land.foot_traffic_score, land.demand_score),
    competition_score: normalizeFinite(land.competition_score, 0),
    risk_score: normalizeFinite(land.risk_score, 0),
    supply_access_score: normalizeFinite(land.supply_access_score, 0),
    best_business_fit: land.best_business_fit,
    linked_business_id: land.linked_business_id,
    linked_business_type: land.linked_business_type,
    ownership_status: land.ownership_status,
  });

  return {
    slot_id: economicSlot.slot_id,
    address: economicSlot.address,
    region: land.region || economicSlot.region || economicSlot.district_category,
    district: land.district || economicSlot.district || null,
    slot_type: economicSlot.slot_type,
    purchase_price: normalizeMoney(land.purchase_price, 0),
    current_value: economicSlot.current_value,
    demand_score: economicSlot.demand_score,
    foot_traffic_score: economicSlot.foot_traffic_score,
    competition_score: economicSlot.competition_score,
    risk_score: economicSlot.risk_score,
    supply_access_score: economicSlot.supply_access_score,
    best_business_fit: economicSlot.best_business_fit,
    linked_business_id: economicSlot.linked_business_id,
    linked_business_type: economicSlot.linked_business_type,
    ownership_status: economicSlot.ownership_status,
  };
}

function sandboxLotToPortfolioLand(
  lot: SandboxPortfolioLot,
  linkedBusinessType: string | null,
): PortfolioOwnedLand | null {
  const slotId = String(lot.tile_key || '').trim();
  if (!slotId) return null;

  const economicSlot = createSlotEconomicRecord({
    slot_id: slotId,
    address: String(lot.address || '').trim() || buildDeterministicPortfolioAddress(slotId, String(lot.district_label || lot.district_key || '').trim() || null),
    region: String(lot.region || '').trim() || null,
    district: String(lot.district_label || lot.district_key || '').trim() || null,
    slot_type: String(lot.zone_type || '').trim() || null,
    purchase_price: normalizeMoney(lot.purchase_price_xgp, 0),
    current_value: normalizeMoney(lot.value_xgp, 0),
    demand_score: lot.demand_score == null ? null : normalizeFinite(lot.demand_score, 0),
    foot_traffic_score: lot.foot_traffic_score == null ? null : normalizeFinite(lot.foot_traffic_score, 0),
    traffic_score: lot.traffic_score == null ? null : normalizeFinite(lot.traffic_score, 0),
    competition_score: lot.competition_score == null ? null : normalizeFinite(lot.competition_score, 0),
    risk_score: lot.risk_score == null ? null : normalizeFinite(lot.risk_score, 0),
    supply_access_score: lot.supply_access_score == null ? null : normalizeFinite(lot.supply_access_score, 0),
    best_business_fit: lot.best_business_fit || null,
    linked_business_id: String(lot.linked_business_id || lot.placed_business_id || '').trim() || null,
    linked_business_type: linkedBusinessType || String(lot.planned_business_type || '').trim() || null,
    ownership_status: String(lot.ownership_status || '').trim()
      || (String(lot.development_stage || '').trim()
        ? `owned_${String(lot.development_stage).trim().toLowerCase()}`
        : 'owned'),
    development_potential: lot.development_potential == null ? null : normalizeFinite(lot.development_potential, 0),
    location_business_multiplier: lot.location_business_multiplier == null ? null : normalizeFinite(lot.location_business_multiplier, 1),
  });

  return {
    slot_id: economicSlot.slot_id,
    address: economicSlot.address,
    region: economicSlot.region || economicSlot.district_category,
    district: economicSlot.district,
    slot_type: economicSlot.slot_type,
    purchase_price: economicSlot.purchase_price,
    current_value: economicSlot.current_value,
    demand_score: economicSlot.demand_score,
    foot_traffic_score: economicSlot.foot_traffic_score,
    competition_score: economicSlot.competition_score,
    risk_score: economicSlot.risk_score,
    supply_access_score: economicSlot.supply_access_score,
    best_business_fit: economicSlot.best_business_fit,
    linked_business_id: economicSlot.linked_business_id,
    linked_business_type: economicSlot.linked_business_type,
    ownership_status: economicSlot.ownership_status,
  };
}

export function mergePortfolioSummaryWithSandbox(
  summary: PortfolioSummary,
  sandboxLots: SandboxPortfolioLot[],
): PortfolioSummary {
  const businessById = new Map(summary.businesses.map((business) => [business.business_id, business]));
  const normalizedOwnedLand = summary.owned_land.map(normalizeSummaryLand);
  const landBySlotId = new Map(normalizedOwnedLand.map((land) => [land.slot_id, land]));

  for (const lot of sandboxLots) {
    const slotId = String(lot.tile_key || '').trim();
    if (!slotId || landBySlotId.has(slotId)) continue;
    const linkedBusinessId = String(lot.linked_business_id || lot.placed_business_id || '').trim() || null;
    const linkedBusinessType = linkedBusinessId
      ? businessById.get(linkedBusinessId)?.business_type || null
      : null;
    const portfolioLand = sandboxLotToPortfolioLand(lot, linkedBusinessType);
    if (portfolioLand) {
      landBySlotId.set(slotId, portfolioLand);
    }
  }

  const mergedLand = Array.from(landBySlotId.values())
    .sort((left, right) => left.address.localeCompare(right.address));
  const mergedBusinesses = summary.businesses.map((business) => {
    const linkedLand = mergedLand.find((land) => land.linked_business_id === business.business_id) || null;
    return {
      ...business,
      linked_slot_id: business.linked_slot_id || linkedLand?.slot_id || null,
      address: business.address || linkedLand?.address || null,
      region: business.region || linkedLand?.region || null,
    };
  });

  const landValue = normalizeMoney(
    mergedLand.length
      ? mergedLand.reduce((sum, land) => sum + normalizeMoney(land.current_value, 0), 0)
      : summary.land_value,
    0,
  );
  const totalAssetsWithoutSandboxLand = normalizeMoney(
    summary.total_assets_without_sandbox_land || (summary.cash + summary.stock_holdings_value + summary.business_value + summary.inventory_value),
    0,
  );
  const totalAssets = normalizeMoney(
    totalAssetsWithoutSandboxLand + landValue,
    0,
  );
  const netWorth = normalizeMoney(totalAssets - summary.debt, 0);

  return {
    ...summary,
    land_value: landValue,
    total_assets_without_sandbox_land: totalAssetsWithoutSandboxLand,
    net_worth_without_sandbox_land: normalizeMoney(summary.net_worth_without_sandbox_land || (totalAssetsWithoutSandboxLand - summary.debt), 0),
    total_assets: totalAssets,
    net_worth: netWorth,
    owned_land: mergedLand,
    businesses: mergedBusinesses,
  };
}

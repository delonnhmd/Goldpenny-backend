import { fetchApiWithFallback } from '@/lib/apiClient';
import { normalizeCurrentDay, normalizeFiniteNumber, normalizeMoneyValue } from '@/lib/economySafety';
import {
  PortfolioBusinessSummary,
  PortfolioOwnedLand,
  PortfolioSummary,
} from '@/lib/portfolioSummary';

function toStringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function normalizeOwnedLand(value: unknown): PortfolioOwnedLand[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const row = (item && typeof item === 'object') ? (item as Record<string, unknown>) : {};
    return {
      slot_id: toStringValue(row.slot_id),
      address: toStringValue(row.address),
      region: toStringValue(row.region, '') || null,
      district: toStringValue(row.district, '') || null,
      slot_type: toStringValue(row.slot_type, '') || null,
      purchase_price: normalizeMoneyValue(row.purchase_price, { allowNegative: false, fallback: 0 }),
      current_value: normalizeMoneyValue(row.current_value, { allowNegative: false, fallback: 0 }),
      demand_score: normalizeFiniteNumber(row.demand_score, { fallback: 0, min: 0, max: 100 }),
      foot_traffic_score: normalizeFiniteNumber(row.foot_traffic_score, { fallback: 0, min: 0, max: 100 }),
      competition_score: normalizeFiniteNumber(row.competition_score, { fallback: 0, min: 0, max: 100 }),
      risk_score: normalizeFiniteNumber(row.risk_score, { fallback: 0, min: 0, max: 100 }),
      supply_access_score: normalizeFiniteNumber(row.supply_access_score, { fallback: 0, min: 0, max: 100 }),
      best_business_fit: (toStringValue(row.best_business_fit, '') || null) as PortfolioOwnedLand['best_business_fit'],
      linked_business_id: toStringValue(row.linked_business_id, '') || null,
      linked_business_type: toStringValue(row.linked_business_type, '') || null,
      ownership_status: toStringValue(row.ownership_status, 'owned'),
    };
  }).filter((item) => item.slot_id);
}

function normalizeBusinesses(value: unknown): PortfolioBusinessSummary[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const row = (item && typeof item === 'object') ? (item as Record<string, unknown>) : {};
    return {
      business_id: toStringValue(row.business_id),
      business_type: toStringValue(row.business_type),
      region: toStringValue(row.region, '') || null,
      linked_slot_id: toStringValue(row.linked_slot_id, '') || null,
      address: toStringValue(row.address, '') || null,
      reputation: normalizeFiniteNumber(row.reputation, { fallback: 0, min: 0, max: 100, round: 'round' }),
      inventory_value: normalizeMoneyValue(row.inventory_value, { allowNegative: false, fallback: 0 }),
      avg_7_day_profit: normalizeMoneyValue(row.avg_7_day_profit, { allowNegative: true, fallback: 0 }),
      estimated_business_value: normalizeMoneyValue(row.estimated_business_value, { allowNegative: false, fallback: 0 }),
      last_net_profit: normalizeMoneyValue(row.last_net_profit, { allowNegative: true, fallback: 0 }),
      last_operated_day: row.last_operated_day == null
        ? null
        : normalizeCurrentDay(row.last_operated_day, 1),
    };
  }).filter((item) => item.business_id);
}

export async function getPortfolioSummary(playerId: string): Promise<PortfolioSummary> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>([
    `/portfolio/player/${playerId}/summary`,
  ]);

  return {
    player_id: toStringValue(raw.player_id, playerId),
    day: normalizeCurrentDay(raw.day, 1),
    cash: normalizeMoneyValue(raw.cash, { allowNegative: true, fallback: 0 }),
    debt: normalizeMoneyValue(raw.debt, { allowNegative: false, fallback: 0 }),
    stock_holdings_value: normalizeMoneyValue(raw.stock_holdings_value, { allowNegative: false, fallback: 0 }),
    land_value: normalizeMoneyValue(raw.land_value, { allowNegative: false, fallback: 0 }),
    business_value: normalizeMoneyValue(raw.business_value, { allowNegative: false, fallback: 0 }),
    inventory_value: normalizeMoneyValue(raw.inventory_value, { allowNegative: false, fallback: 0 }),
    total_assets: normalizeMoneyValue(raw.total_assets, { allowNegative: true, fallback: 0 }),
    net_worth: normalizeMoneyValue(raw.net_worth, { allowNegative: true, fallback: 0 }),
    total_assets_without_sandbox_land: normalizeMoneyValue(raw.total_assets_without_sandbox_land, { allowNegative: true, fallback: 0 }),
    net_worth_without_sandbox_land: normalizeMoneyValue(raw.net_worth_without_sandbox_land, { allowNegative: true, fallback: 0 }),
    latest_business_profit: normalizeMoneyValue(raw.latest_business_profit, { allowNegative: true, fallback: 0 }),
    trailing_7d_business_profit: normalizeMoneyValue(raw.trailing_7d_business_profit, { allowNegative: true, fallback: 0 }),
    active_business_count: normalizeFiniteNumber(raw.active_business_count, { fallback: 0, min: 0, round: 'floor' }),
    owned_land: normalizeOwnedLand(raw.owned_land),
    businesses: normalizeBusinesses(raw.businesses),
  };
}

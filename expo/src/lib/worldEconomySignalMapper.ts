// Gold Penny — centralized backend-to-player economy signal translator.
// All mapping logic lives here so it stays deterministic and easy to tune.
// Rule: backend raw keys come in, player-readable sentences go out.
// No UI imports; no side effects; pure functions only.

import { DailyEconomyBriefResponse } from '@/types/economyPresentation';
import { SupplyChainSummaryResponse } from '@/types/supplyChain';

// ── Supply-chain node key → player-readable label ─────────────────────────────

const BOTTLENECK_LABEL: Record<string, string> = {
  transport_hub: 'Logistics hub',
  produce_market: 'Produce market',
  distribution_center: 'Distribution centre',
  cold_storage: 'Cold storage',
  port_terminal: 'Port operations',
  fuel_depot: 'Fuel supply',
  grains_warehouse: 'Grain stores',
  food_processing: 'Food processing',
  retail_hub: 'Retail supply hub',
  local_market: 'Local market',
};

// Supply-chain node key → player-action hint when that node is under pressure
const BOTTLENECK_OPPORTUNITY: Record<string, string> = {
  transport_hub: 'Delivery and logistics shifts are in higher demand',
  produce_market: 'Fresh produce sourcing and fruit business opportunity opening',
  distribution_center: 'Stock-up before delays; bulk-buy window available',
  cold_storage: 'Food preservation actions and stock management favoured',
  port_terminal: 'Local sourcing alternatives and import substitutes opening up',
  fuel_depot: 'Fuel-light routes and nearby work preferred over long commutes',
  grains_warehouse: 'Grain-alternative baskets and local staples opportunity',
  food_processing: 'Fresh market direct-purchase alternatives are favoured this cycle',
  retail_hub: 'Independent sourcing and direct-to-supplier paths available',
  local_market: 'Local market activity elevated — street-trade opportunity up',
};

// ── Basket key → player-readable label ───────────────────────────────────────

const BASKET_LABEL: Record<string, string> = {
  produce: 'Fresh produce',
  grains: 'Grains and staples',
  dairy: 'Dairy',
  proteins: 'Meat and proteins',
  beverages: 'Beverages',
  snacks: 'Snacks and packaged goods',
  personal_care: 'Personal care',
  household: 'Household essentials',
  essentials: 'Essential groceries',
};

// ── Job key → player-readable label ──────────────────────────────────────────

const JOB_LABEL: Record<string, string> = {
  delivery_driver: 'Delivery driver',
  market_stall: 'Market stall operator',
  fruit_shop: 'Fruit shop owner',
  food_truck: 'Food truck operator',
  warehouse_worker: 'Warehouse worker',
  logistics_coordinator: 'Logistics coordinator',
  street_vendor: 'Street vendor',
  courier: 'Courier',
};

// ── Private helpers ───────────────────────────────────────────────────────────

function formatKey(key: string): string {
  return String(key || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function bottleneckLabel(key: string): string {
  return BOTTLENECK_LABEL[key] || formatKey(key);
}

function basketLabel(key: string): string {
  return BASKET_LABEL[key] || formatKey(key);
}

function jobLabel(key: string): string {
  return JOB_LABEL[key] || formatKey(key);
}

function bottleneckOpportunityHint(key: string): string {
  return BOTTLENECK_OPPORTUNITY[key] || `${bottleneckLabel(key)} pressure — check local opportunities`;
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Build up to three short impact bullets for the DailyBriefCard "Driving Signals" section.
 * Reads top_bottlenecks, top_basket_movers, and top_job_changes from the backend brief.
 * Returns an empty array when the brief is missing or all signal lists are empty.
 */
export function buildDailyBriefImpactBullets(
  daily_brief: DailyEconomyBriefResponse | null | undefined,
): string[] {
  if (!daily_brief) return [];

  const bullets: string[] = [];

  const bottlenecks = (daily_brief.top_bottlenecks || []).filter(Boolean).slice(0, 2);
  if (bottlenecks.length > 0) {
    const readable = bottlenecks.map(bottleneckLabel).join(' and ');
    bullets.push(`${readable} under pressure today`);
  }

  const basketMovers = (daily_brief.top_basket_movers || []).filter(Boolean).slice(0, 2);
  if (basketMovers.length > 0) {
    const readable = basketMovers.map(basketLabel).join(', ');
    bullets.push(`${readable} prices moving this cycle`);
  }

  const jobChanges = (daily_brief.top_job_changes || []).filter(Boolean).slice(0, 1);
  if (jobChanges.length > 0) {
    const readable = jobChanges.map(jobLabel).join(', ');
    bullets.push(`${readable} conditions shifting`);
  }

  return bullets.slice(0, 3);
}

/**
 * Translate top backend bottleneck nodes into player-readable opportunity hints.
 * Used to populate top_opportunities when player_opportunities is empty.
 */
export function buildBottleneckOpportunityHints(
  bottlenecks: string[],
): { title: string; description: string }[] {
  return (bottlenecks || []).filter(Boolean).slice(0, 2).map((key) => ({
    title: bottleneckLabel(key),
    description: bottleneckOpportunityHint(key),
  }));
}

/**
 * Translate top backend job change keys into player-readable opportunity hints.
 * Used to supplement top_opportunities when player_opportunities is sparse.
 */
export function buildJobChangeHints(
  jobChanges: string[],
): { title: string; description: string }[] {
  return (jobChanges || []).filter(Boolean).slice(0, 2).map((key) => ({
    title: `${jobLabel(key)} demand`,
    description: `${jobLabel(key)} activity is shifting — check today's action hub`,
  }));
}

/**
 * Translate top basket mover keys into player-readable caution signals.
 * Used to populate top_risks when player_warnings is empty.
 */
export function buildBasketPressureSignals(
  basketMovers: string[],
): { title: string; description: string }[] {
  return (basketMovers || []).filter(Boolean).slice(0, 2).map((key) => ({
    title: `${basketLabel(key)} price pressure`,
    description: `${basketLabel(key)} costs elevated this cycle — adjust basket accordingly`,
  }));
}

/**
 * Derive a single player-facing line from the supply chain best job opportunity field.
 * Returns null when no job opportunity is present.
 */
export function supplyChainJobOpportunityLine(
  summary: SupplyChainSummaryResponse | null | undefined,
): string | null {
  if (!summary?.best_job_opportunity) return null;
  const label = jobLabel(summary.best_job_opportunity);
  return `${label} is the top opportunity right now based on supply-chain pressure`;
}

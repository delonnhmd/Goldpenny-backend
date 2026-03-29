import { BusinessMarginsResponse, CommutePressureResponse, MarketOverviewResponse, PriceTrendsResponse } from '@/types/economyPresentation';
import { CommitmentSummaryResponse } from '@/types/commitment';
import { StrategyRecommendationResponse } from '@/types/strategicPlanning';
import { SupplyChainSummaryResponse } from '@/types/supplyChain';
import { LocalPressureSummaryResponse, WorldNarrativeResponse, WorldPatternsResponse } from '@/types/worldMemory';

function safeLine(value: string | null | undefined, fallback: string): string {
  const next = String(value || '').trim();
  return next || fallback;
}

export function buildEconomySummary(
  market: MarketOverviewResponse | null,
  prices: PriceTrendsResponse | null,
  commute: CommutePressureResponse | null,
  supplyChain?: SupplyChainSummaryResponse | null,
): string {
  const mood = safeLine(market?.current_market_mood, 'mixed');
  const topBasket = prices?.items?.[0];
  const basketLine = topBasket
    ? `${topBasket.basket_key.replace(/_/g, ' ')} ${safeLine(topBasket.short_term_trend, 'flat')}`
    : 'basket pressure mixed';
  const commuteLine = commute
    ? safeLine(commute.time_impact_label, 'commute stable')
    : 'commute stable';
  const supplyLine = supplyChain?.short_summary ? safeLine(supplyChain.short_summary, '') : '';
  return `${mood}. ${basketLine}. ${commuteLine}.${supplyLine ? ` ${supplyLine}` : ''}`;
}

export function buildBusinessSummary(
  margins: BusinessMarginsResponse | null,
  _unused?: unknown,
): string {
  const fruit = margins?.items?.find((item) => item.business_key === 'fruit_shop');
  const truck = margins?.items?.find((item) => item.business_key === 'food_truck');
  const fruitLine = fruit ? `Fruit Shop ${safeLine(fruit.margin_outlook, 'mixed')}` : 'Fruit Shop mixed';
  const truckLine = truck ? `Food Truck ${safeLine(truck.margin_outlook, 'mixed')}` : 'Food Truck mixed';
  return `${fruitLine}. ${truckLine}.`;
}

export function buildPlanningSummary(
  recommendation: StrategyRecommendationResponse | null,
  commitment: CommitmentSummaryResponse | null,
): string {
  const plan = safeLine(recommendation?.recommended_plan_title, 'Review options');
  const risk = safeLine(recommendation?.biggest_risk, 'Manage daily pressure');
  const commitmentLine = commitment?.active_commitment?.status === 'active'
    ? `Commitment active: ${safeLine(commitment.active_commitment.title, 'Current plan')}`
    : 'No active commitment';
  return `${plan}. Risk: ${risk}. ${commitmentLine}.`;
}

export function buildWorldSummary(
  narrative: WorldNarrativeResponse | null,
  patterns: WorldPatternsResponse | null,
  local: LocalPressureSummaryResponse | null,
): string {
  const head = safeLine(narrative?.headline, 'World pressure is evolving');
  const patternCount = Array.isArray(patterns?.items) ? patterns.items.length : 0;
  const localLine = safeLine(local?.short_summary, 'Local conditions are steady');
  return `${head}. ${patternCount} active pattern${patternCount === 1 ? '' : 's'}. ${localLine}`;
}


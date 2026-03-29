import { fetchApiWithFallback } from '@/lib/apiClient';
import {
  BusinessMarginsResponse,
  CommutePressureResponse,
  EconomyPresentationSummaryResponse,
  FutureOpportunityTeasersResponse,
  MarketOverviewResponse,
  PlayerEconomyExplainerResponse,
  PriceTrendsResponse,
} from '@/types/economyPresentation';


function toResponseDateValue(asOfDate?: string | null): string {
  if (!asOfDate) return '';
  return encodeURIComponent(asOfDate);
}

function withDateParam(path: string, asOfDate?: string | null): string {
  const dateValue = toResponseDateValue(asOfDate);
  if (!dateValue) return path;
  return `${path}?as_of_date=${dateValue}`;
}

export async function getMarketOverview(
  playerId: string,
  asOfDate?: string | null,
): Promise<MarketOverviewResponse> {
  return fetchApiWithFallback<MarketOverviewResponse>([
    withDateParam(`/economy-presentation/player/${playerId}/market-overview`, asOfDate),
  ]);
}

export async function getPriceTrends(
  playerId: string,
  asOfDate?: string | null,
): Promise<PriceTrendsResponse> {
  return fetchApiWithFallback<PriceTrendsResponse>([
    withDateParam(`/economy-presentation/player/${playerId}/price-trends`, asOfDate),
  ]);
}

export async function getBusinessMargins(
  playerId: string,
  asOfDate?: string | null,
): Promise<BusinessMarginsResponse> {
  return fetchApiWithFallback<BusinessMarginsResponse>([
    withDateParam(`/economy-presentation/player/${playerId}/business-margins`, asOfDate),
  ]);
}

export async function getCommutePressure(
  playerId: string,
  asOfDate?: string | null,
): Promise<CommutePressureResponse> {
  return fetchApiWithFallback<CommutePressureResponse>([
    withDateParam(`/economy-presentation/player/${playerId}/commute-pressure`, asOfDate),
  ]);
}

export async function getEconomyExplainer(
  playerId: string,
  asOfDate?: string | null,
): Promise<PlayerEconomyExplainerResponse> {
  return fetchApiWithFallback<PlayerEconomyExplainerResponse>([
    withDateParam(`/economy-presentation/player/${playerId}/explainer`, asOfDate),
  ]);
}

export async function getFutureTeasers(
  playerId: string,
  asOfDate?: string | null,
): Promise<FutureOpportunityTeasersResponse> {
  return fetchApiWithFallback<FutureOpportunityTeasersResponse>([
    withDateParam(`/economy-presentation/player/${playerId}/future-teasers`, asOfDate),
  ]);
}

export async function getEconomyPresentationSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<EconomyPresentationSummaryResponse> {
  return fetchApiWithFallback<EconomyPresentationSummaryResponse>([
    withDateParam(`/economy-presentation/player/${playerId}/summary`, asOfDate),
  ]);
}

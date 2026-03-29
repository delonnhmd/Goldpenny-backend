import { fetchApiWithFallback } from '@/lib/apiClient';
import {
  BusinessPlanResponse,
  DebtVsGrowthResponse,
  FuturePreparationResponse,
  HousingTradeoffResponse,
  RecoveryVsPushResponse,
  ShortHorizonPlansResponse,
  StrategicPlanningSummaryResponse,
  StrategyRecommendationResponse,
} from '@/types/strategicPlanning';


function toResponseDateValue(asOfDate?: string | null): string {
  if (!asOfDate) return '';
  return encodeURIComponent(asOfDate);
}

function withDateParam(path: string, asOfDate?: string | null): string {
  const dateValue = toResponseDateValue(asOfDate);
  if (!dateValue) return path;
  return `${path}?as_of_date=${dateValue}`;
}

export async function getShortHorizonPlans(
  playerId: string,
  asOfDate?: string | null,
): Promise<ShortHorizonPlansResponse> {
  return fetchApiWithFallback<ShortHorizonPlansResponse>([
    withDateParam(`/strategic-planning/player/${playerId}/plans`, asOfDate),
  ]);
}

export async function getHousingTradeoff(
  playerId: string,
  asOfDate?: string | null,
): Promise<HousingTradeoffResponse> {
  return fetchApiWithFallback<HousingTradeoffResponse>([
    withDateParam(`/strategic-planning/player/${playerId}/housing-tradeoff`, asOfDate),
  ]);
}

export async function getDebtVsGrowth(
  playerId: string,
  asOfDate?: string | null,
): Promise<DebtVsGrowthResponse> {
  return fetchApiWithFallback<DebtVsGrowthResponse>([
    withDateParam(`/strategic-planning/player/${playerId}/debt-vs-growth`, asOfDate),
  ]);
}

export async function getBusinessPlan(
  playerId: string,
  asOfDate?: string | null,
): Promise<BusinessPlanResponse> {
  return fetchApiWithFallback<BusinessPlanResponse>([
    withDateParam(`/strategic-planning/player/${playerId}/business-plan`, asOfDate),
  ]);
}

export async function getRecoveryVsPush(
  playerId: string,
  asOfDate?: string | null,
): Promise<RecoveryVsPushResponse> {
  return fetchApiWithFallback<RecoveryVsPushResponse>([
    withDateParam(`/strategic-planning/player/${playerId}/recovery-vs-push`, asOfDate),
  ]);
}

export async function getStrategyRecommendation(
  playerId: string,
  asOfDate?: string | null,
): Promise<StrategyRecommendationResponse> {
  return fetchApiWithFallback<StrategyRecommendationResponse>([
    withDateParam(`/strategic-planning/player/${playerId}/recommendation`, asOfDate),
  ]);
}

export async function getFuturePreparation(
  playerId: string,
  asOfDate?: string | null,
): Promise<FuturePreparationResponse> {
  return fetchApiWithFallback<FuturePreparationResponse>([
    withDateParam(`/strategic-planning/player/${playerId}/future-preparation`, asOfDate),
  ]);
}

export async function getStrategicPlanningSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<StrategicPlanningSummaryResponse> {
  return fetchApiWithFallback<StrategicPlanningSummaryResponse>([
    withDateParam(`/strategic-planning/player/${playerId}/summary`, asOfDate),
  ]);
}

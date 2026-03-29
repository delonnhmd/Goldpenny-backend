import { fetchApi } from '@/lib/apiClient';
import {
  LocalCompetitionStateResponse,
  LocalOpportunityPressureResponse,
  PopulationPressureSummaryResponse,
  PopulationResponseSummaryResponse,
  RegionHeatSummaryResponse,
  RegionPopulationStateResponse,
} from '@/types/populationPressure';


function toResponseDateValue(asOfDate?: string | null): string {
  if (!asOfDate) return '';
  return encodeURIComponent(asOfDate);
}

function withDateParam(path: string, asOfDate?: string | null): string {
  const dateValue = toResponseDateValue(asOfDate);
  if (!dateValue) return path;
  return `${path}?as_of_date=${dateValue}`;
}

export async function getRegionPopulationState(
  playerId: string,
  asOfDate?: string | null,
): Promise<RegionPopulationStateResponse> {
  return fetchApi<RegionPopulationStateResponse>(
    withDateParam(`/population/player/${playerId}/region-state`, asOfDate),
  );
}

export async function getOpportunityPressure(
  playerId: string,
  asOfDate?: string | null,
): Promise<LocalOpportunityPressureResponse> {
  return fetchApi<LocalOpportunityPressureResponse>(
    withDateParam(`/population/player/${playerId}/opportunity-pressure`, asOfDate),
  );
}

export async function getCompetitionState(
  playerId: string,
  asOfDate?: string | null,
): Promise<LocalCompetitionStateResponse> {
  return fetchApi<LocalCompetitionStateResponse>(
    withDateParam(`/population/player/${playerId}/competition-state`, asOfDate),
  );
}

export async function getRegionHeat(
  playerId: string,
  asOfDate?: string | null,
): Promise<RegionHeatSummaryResponse> {
  return fetchApi<RegionHeatSummaryResponse>(
    withDateParam(`/population/player/${playerId}/region-heat`, asOfDate),
  );
}

export async function getPopulationResponseSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<PopulationResponseSummaryResponse> {
  return fetchApi<PopulationResponseSummaryResponse>(
    withDateParam(`/population/player/${playerId}/response-summary`, asOfDate),
  );
}

export async function getPopulationPressureSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<PopulationPressureSummaryResponse> {
  return fetchApi<PopulationPressureSummaryResponse>(
    withDateParam(`/population/player/${playerId}/summary`, asOfDate),
  );
}

export async function refreshPopulationPressure(
  playerId: string,
  asOfDate?: string | null,
): Promise<RegionPopulationStateResponse> {
  return fetchApi<RegionPopulationStateResponse>(
    withDateParam(`/population/player/${playerId}/refresh`, asOfDate),
    { method: 'POST' },
  );
}

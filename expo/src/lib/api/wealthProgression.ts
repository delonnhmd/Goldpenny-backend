import { fetchApi } from '@/lib/apiClient';
import {
  AssetProgressionStateResponse,
  NetWorthSummaryResponse,
  SavingsCapacityStateResponse,
  WealthActionsEvaluationResponse,
  WealthMomentumSummaryResponse,
  WealthProfileResponse,
} from '@/types/wealthProgression';


function withDate(path: string, asOfDate?: string | null): string {
  if (!asOfDate) return path;
  return `${path}?as_of_date=${encodeURIComponent(asOfDate)}`;
}

export async function getWealthProfile(
  playerId: string,
  asOfDate?: string | null,
): Promise<WealthProfileResponse> {
  return fetchApi<WealthProfileResponse>(
    withDate(`/wealth/player/${playerId}/profile`, asOfDate),
  );
}

export async function getSavingsCapacityState(
  playerId: string,
  asOfDate?: string | null,
): Promise<SavingsCapacityStateResponse> {
  return fetchApi<SavingsCapacityStateResponse>(
    withDate(`/wealth/player/${playerId}/savings-capacity`, asOfDate),
  );
}

export async function getAssetProgressionState(
  playerId: string,
  asOfDate?: string | null,
): Promise<AssetProgressionStateResponse> {
  return fetchApi<AssetProgressionStateResponse>(
    withDate(`/wealth/player/${playerId}/asset-progression`, asOfDate),
  );
}

export async function getWealthActionEvaluation(
  playerId: string,
  asOfDate?: string | null,
): Promise<WealthActionsEvaluationResponse> {
  return fetchApi<WealthActionsEvaluationResponse>(
    withDate(`/wealth/player/${playerId}/action-evaluation`, asOfDate),
  );
}

export async function getNetWorthSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<NetWorthSummaryResponse> {
  return fetchApi<NetWorthSummaryResponse>(
    withDate(`/wealth/player/${playerId}/net-worth-summary`, asOfDate),
  );
}

export async function getWealthMomentumSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<WealthMomentumSummaryResponse> {
  return fetchApi<WealthMomentumSummaryResponse>(
    withDate(`/wealth/player/${playerId}/momentum-summary`, asOfDate),
  );
}

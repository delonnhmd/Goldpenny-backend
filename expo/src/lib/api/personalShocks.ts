import { fetchApi } from '@/lib/apiClient';
import {
  PersonalLifeEventResponse,
  PersonalRiskStateResponse,
  PersonalShockProfileResponse,
  PersonalShockSummaryResponse,
  PersonalShockSystemSummaryResponse,
  PlayerResilienceSummaryResponse,
  RecoveryStateResponse,
} from '@/types/personalShocks';


function withDate(path: string, asOfDate?: string | null): string {
  if (!asOfDate) return path;
  return `${path}?as_of_date=${encodeURIComponent(asOfDate)}`;
}

export async function getPersonalShockProfile(
  playerId: string,
  asOfDate?: string | null,
): Promise<PersonalShockProfileResponse> {
  return fetchApi<PersonalShockProfileResponse>(
    withDate(`/personal/player/${playerId}/shock-profile`, asOfDate),
  );
}

export async function getPersonalRiskState(
  playerId: string,
  asOfDate?: string | null,
): Promise<PersonalRiskStateResponse> {
  return fetchApi<PersonalRiskStateResponse>(
    withDate(`/personal/player/${playerId}/risk-state`, asOfDate),
  );
}

export async function getRecentPersonalEvent(
  playerId: string,
  asOfDate?: string | null,
): Promise<PersonalLifeEventResponse> {
  return fetchApi<PersonalLifeEventResponse>(
    withDate(`/personal/player/${playerId}/recent-event`, asOfDate),
  );
}

export async function getPersonalRecoveryState(playerId: string): Promise<RecoveryStateResponse> {
  return fetchApi<RecoveryStateResponse>(`/personal/player/${playerId}/recovery-state`);
}

export async function getPersonalResilienceSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<PlayerResilienceSummaryResponse> {
  return fetchApi<PlayerResilienceSummaryResponse>(
    withDate(`/personal/player/${playerId}/resilience-summary`, asOfDate),
  );
}

export async function getPersonalShockSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<PersonalShockSummaryResponse> {
  return fetchApi<PersonalShockSummaryResponse>(
    withDate(`/personal/player/${playerId}/shock-summary`, asOfDate),
  );
}

export async function getPersonalShockSystemSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<PersonalShockSystemSummaryResponse> {
  return fetchApi<PersonalShockSystemSummaryResponse>(
    withDate(`/personal/player/${playerId}/summary`, asOfDate),
  );
}


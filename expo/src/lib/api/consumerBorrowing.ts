import { fetchApi } from '@/lib/apiClient';
import {
  BorrowingDecisionRequest,
  BorrowingDecisionResponse,
  BorrowingEligibilityProfileResponse,
  BorrowingOptionsResponse,
  BorrowingPressureSummaryResponse,
  BorrowingRiskSummaryResponse,
  ConsumerBorrowingSystemSummaryResponse,
  EmergencyLiquidityStateResponse,
  PlayerBorrowingHistoryResponse,
  PlayerLoanAccountsResponse,
} from '@/types/consumerBorrowing';


function withDate(path: string, asOfDate?: string | null): string {
  if (!asOfDate) return path;
  return `${path}?as_of_date=${encodeURIComponent(asOfDate)}`;
}

export async function getBorrowingEligibilityProfile(
  playerId: string,
  asOfDate?: string | null,
): Promise<BorrowingEligibilityProfileResponse> {
  return fetchApi<BorrowingEligibilityProfileResponse>(
    withDate(`/borrowing/player/${playerId}/eligibility-profile`, asOfDate),
  );
}

export async function getEmergencyLiquidityState(
  playerId: string,
  asOfDate?: string | null,
): Promise<EmergencyLiquidityStateResponse> {
  return fetchApi<EmergencyLiquidityStateResponse>(
    withDate(`/borrowing/player/${playerId}/liquidity-state`, asOfDate),
  );
}

export async function getBorrowingOptions(
  playerId: string,
  asOfDate?: string | null,
): Promise<BorrowingOptionsResponse> {
  return fetchApi<BorrowingOptionsResponse>(
    withDate(`/borrowing/player/${playerId}/options`, asOfDate),
  );
}

export async function getBorrowingRiskSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<BorrowingRiskSummaryResponse> {
  return fetchApi<BorrowingRiskSummaryResponse>(
    withDate(`/borrowing/player/${playerId}/risk-summary`, asOfDate),
  );
}

export async function getBorrowingPressureSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<BorrowingPressureSummaryResponse> {
  return fetchApi<BorrowingPressureSummaryResponse>(
    withDate(`/borrowing/player/${playerId}/pressure-summary`, asOfDate),
  );
}

export async function acceptBorrowingOffer(
  playerId: string,
  payload: BorrowingDecisionRequest,
): Promise<BorrowingDecisionResponse> {
  return fetchApi<BorrowingDecisionResponse>(
    `/borrowing/player/${playerId}/accept-offer`,
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export async function getBorrowingLoanAccounts(
  playerId: string,
): Promise<PlayerLoanAccountsResponse> {
  return fetchApi<PlayerLoanAccountsResponse>(`/borrowing/player/${playerId}/loan-accounts`);
}

export async function getBorrowingHistory(
  playerId: string,
  asOfDate?: string | null,
): Promise<PlayerBorrowingHistoryResponse> {
  return fetchApi<PlayerBorrowingHistoryResponse>(
    withDate(`/borrowing/player/${playerId}/history`, asOfDate),
  );
}

export async function getConsumerBorrowingSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<ConsumerBorrowingSystemSummaryResponse> {
  return fetchApi<ConsumerBorrowingSystemSummaryResponse>(
    withDate(`/borrowing/player/${playerId}/summary`, asOfDate),
  );
}

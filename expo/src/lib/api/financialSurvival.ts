import { fetchApi } from '@/lib/apiClient';
import {
  CreditImpactSummaryResponse,
  DelinquencyStateResponse,
  FinancialSurvivalPaymentHistoryResponse,
  FinancialSurvivalSummaryResponse,
  FinancialSurvivalSystemSummaryResponse,
  PaymentRiskStateResponse,
  PlayerObligationProfileResponse,
} from '@/types/financialSurvival';


function withDate(path: string, asOfDate?: string | null): string {
  if (!asOfDate) return path;
  return `${path}?as_of_date=${encodeURIComponent(asOfDate)}`;
}

export async function getObligationProfile(
  playerId: string,
  asOfDate?: string | null,
): Promise<PlayerObligationProfileResponse> {
  return fetchApi<PlayerObligationProfileResponse>(
    withDate(`/financial/player/${playerId}/obligation-profile`, asOfDate),
  );
}

export async function getPaymentRiskState(
  playerId: string,
  asOfDate?: string | null,
): Promise<PaymentRiskStateResponse> {
  return fetchApi<PaymentRiskStateResponse>(
    withDate(`/financial/player/${playerId}/payment-risk`, asOfDate),
  );
}

export async function getDelinquencyState(
  playerId: string,
  asOfDate?: string | null,
): Promise<DelinquencyStateResponse> {
  return fetchApi<DelinquencyStateResponse>(
    withDate(`/financial/player/${playerId}/delinquency-state`, asOfDate),
  );
}

export async function getCreditImpact(
  playerId: string,
  asOfDate?: string | null,
): Promise<CreditImpactSummaryResponse> {
  return fetchApi<CreditImpactSummaryResponse>(
    withDate(`/financial/player/${playerId}/credit-impact`, asOfDate),
  );
}

export async function getFinancialSurvivalSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<FinancialSurvivalSummaryResponse> {
  return fetchApi<FinancialSurvivalSummaryResponse>(
    withDate(`/financial/player/${playerId}/survival-summary`, asOfDate),
  );
}

export async function getFinancialPaymentHistory(
  playerId: string,
  asOfDate?: string | null,
): Promise<FinancialSurvivalPaymentHistoryResponse> {
  return fetchApi<FinancialSurvivalPaymentHistoryResponse>(
    withDate(`/financial/player/${playerId}/payment-history`, asOfDate),
  );
}

export async function getFinancialSurvivalSystemSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<FinancialSurvivalSystemSummaryResponse> {
  return fetchApi<FinancialSurvivalSystemSummaryResponse>(
    withDate(`/financial/player/${playerId}/summary`, asOfDate),
  );
}


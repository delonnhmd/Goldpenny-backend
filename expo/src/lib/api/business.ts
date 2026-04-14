// Gold Penny — business API client.
// Targets Step 15 player-id routes (no auth required).
import { fetchApiWithFallback } from '@/lib/apiClient';
import { PlayerBusinessesResponse } from '@/types/business';

export async function getPlayerBusinesses(playerId: string): Promise<PlayerBusinessesResponse> {
  return fetchApiWithFallback<PlayerBusinessesResponse>([
    `/business/player/${playerId}`,
  ]);
}

export interface OpenBusinessResponse {
  message: string;
  business_id: string;
  display_name: string;
  startup_cost: number;
  balance_before: number;
  balance_after: number;
  created_day: number;
}

export async function openBusiness(businessId: string): Promise<OpenBusinessResponse> {
  return fetchApiWithFallback<OpenBusinessResponse>([
    '/business/open',
  ], {
    method: 'POST',
    body: JSON.stringify({ business_id: businessId }),
  });
}

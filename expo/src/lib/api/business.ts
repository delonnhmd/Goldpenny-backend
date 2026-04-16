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

export async function openBusiness(businessId: string, playerId?: string): Promise<OpenBusinessResponse> {
  const paths: string[] = [];
  if (playerId) {
    paths.push(`/business/player/${playerId}/open`);
  }
  paths.push('/business/open');
  return fetchApiWithFallback<OpenBusinessResponse>(paths, {
    method: 'POST',
    body: JSON.stringify({ business_id: businessId }),
  });
}

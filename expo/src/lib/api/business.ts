// Gold Penny — business API client.
// Targets Step 15 player-id routes (no auth required).
import { fetchApiWithFallback } from '@/lib/apiClient';
import { PlayerBusinessesResponse } from '@/types/business';

export async function getPlayerBusinesses(playerId: string): Promise<PlayerBusinessesResponse> {
  return fetchApiWithFallback<PlayerBusinessesResponse>([
    `/business/player/${playerId}`,
  ]);
}

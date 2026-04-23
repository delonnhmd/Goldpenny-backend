// Gold Penny — business API client.
// Targets Step 15 player-id routes (no auth required).
import { fetchApiWithFallback } from '@/lib/apiClient';
import {
  PlayerBusinessesResponse,
  SupplierInventoryPurchaseResponse,
  SupplierItemsResponse,
} from '@/types/business';

function withAsOfDate(path: string, asOfDate?: string | null): string {
  if (!asOfDate) return path;
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}as_of_date=${encodeURIComponent(asOfDate)}`;
}

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

export async function getSupplierItems(
  businessType: string,
  asOfDate?: string | null,
): Promise<SupplierItemsResponse> {
  const path = withAsOfDate(
    `/business/supplier/items?business_type=${encodeURIComponent(String(businessType || ''))}`,
    asOfDate,
  );
  return fetchApiWithFallback<SupplierItemsResponse>([path]);
}

export interface SupplierInventoryPurchaseLineInput {
  item_id: string;
  quantity: number;
}

export async function buyBusinessInventory(
  playerId: string,
  businessId: string,
  items: SupplierInventoryPurchaseLineInput[],
  asOfDate?: string | null,
): Promise<SupplierInventoryPurchaseResponse> {
  return fetchApiWithFallback<SupplierInventoryPurchaseResponse>([
    `/business/player/${playerId}/business/${businessId}/buy-inventory`,
  ], {
    method: 'POST',
    body: JSON.stringify({
      as_of_date: asOfDate ?? null,
      items,
    }),
  });
}

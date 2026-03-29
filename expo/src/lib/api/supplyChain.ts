// Step 43 — Supply Chain Graph + Bottleneck Opportunity Engine API client

import { fetchApi } from '@/lib/apiClient';
import {
  BasketSupplyMultiplierResponse,
  JobPressureResponse,
  SupplyChainBottleneckResponse,
  SupplyChainNodeStateResponse,
  SupplyChainStoryResponse,
  SupplyChainSummaryResponse,
} from '@/types/supplyChain';


function regionParam(region?: string): string {
  return region ? `?region=${encodeURIComponent(region)}` : '';
}

// ---------------------------------------------------------------------------
// 1. Physical node availability states
// ---------------------------------------------------------------------------

export async function getSupplyChainNodes(
  day: number,
  region?: string,
): Promise<SupplyChainNodeStateResponse[]> {
  return fetchApi(`/supply-chain/day/${day}/nodes${regionParam(region)}`);
}

// ---------------------------------------------------------------------------
// 2. Bottleneck detection
// ---------------------------------------------------------------------------

export async function getSupplyChainBottlenecks(
  day: number,
  region?: string,
  threshold: number = 0.95,
): Promise<SupplyChainBottleneckResponse[]> {
  const params = new URLSearchParams();
  if (region) params.set('region', region);
  params.set('threshold', String(threshold));
  const qs = params.toString() ? `?${params.toString()}` : '';
  return fetchApi(`/supply-chain/day/${day}/bottlenecks${qs}`);
}

// ---------------------------------------------------------------------------
// 3. Basket supply cost multipliers
// ---------------------------------------------------------------------------

export async function getBasketSupplyMultipliers(
  day: number,
  region?: string,
): Promise<BasketSupplyMultiplierResponse[]> {
  return fetchApi(`/supply-chain/day/${day}/basket-multipliers${regionParam(region)}`);
}

// ---------------------------------------------------------------------------
// 4. Job pressure from bottlenecks
// ---------------------------------------------------------------------------

export async function getJobPressureFromBottlenecks(
  day: number,
  region?: string,
): Promise<JobPressureResponse[]> {
  return fetchApi(`/supply-chain/day/${day}/job-pressure${regionParam(region)}`);
}

// ---------------------------------------------------------------------------
// 5. Full daily supply chain summary
// ---------------------------------------------------------------------------

export async function getSupplyChainSummary(
  day: number,
  region?: string,
): Promise<SupplyChainSummaryResponse> {
  return fetchApi(`/supply-chain/day/${day}/summary${regionParam(region)}`);
}

// ---------------------------------------------------------------------------
// 6. Narrative story summary
// ---------------------------------------------------------------------------

export async function getSupplyChainStory(
  day: number,
  region?: string,
): Promise<SupplyChainStoryResponse> {
  return fetchApi(`/supply-chain/day/${day}/story${regionParam(region)}`);
}

// ---------------------------------------------------------------------------
// 7. Compute + persist daily snapshot (admin / day-progression use)
// ---------------------------------------------------------------------------

export async function computeSupplyChainSnapshot(
  day: number,
  region?: string,
): Promise<SupplyChainSummaryResponse> {
  const qs = regionParam(region);
  return fetchApi(`/supply-chain/day/${day}/compute${qs}`, { method: 'POST' });
}

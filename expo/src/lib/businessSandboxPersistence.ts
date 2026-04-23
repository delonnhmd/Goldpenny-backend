import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  buildSlotAddress,
  createEmptyBusinessSandboxState,
  estimateSlotCurrentValue,
  estimateSlotDemandScore,
} from '@/lib/businessSandbox';
import type { BusinessSandboxState } from '@/types/business';

const BUSINESS_SANDBOX_STORAGE_KEY = (playerId: string) => `goldpenny:business:sandbox:${playerId}`;

function inferRegionId(tileKey: string, districtKey: string | null): string | null {
  if (districtKey) return districtKey;
  const prefix = String(tileKey || '').split(':')[0];
  return prefix || null;
}

function inferRegionKind(regionId: string | null, explicitRegion: unknown): string | null {
  if (explicitRegion != null && String(explicitRegion).trim()) {
    return String(explicitRegion).trim();
  }
  const raw = String(regionId || '').toLowerCase();
  if (raw.includes('downtown')) return 'downtown';
  if (raw.includes('river')) return 'riverside';
  if (raw.includes('harbor')) return 'industrial';
  return raw ? 'suburban' : null;
}

function sanitizeState(value: unknown, playerId: string): BusinessSandboxState | null {
  if (!value || typeof value !== 'object') return null;

  const version = Number((value as { version?: unknown }).version);
  const storedPlayerId = String((value as { player_id?: unknown }).player_id || '').trim();
  if (version !== 1 || storedPlayerId !== playerId) return null;

  const ownedLotsRaw = Array.isArray((value as { owned_lots?: unknown }).owned_lots)
    ? (value as { owned_lots: unknown[] }).owned_lots
    : [];
  const businessLinksRaw = Array.isArray((value as { business_market_links?: unknown }).business_market_links)
    ? (value as { business_market_links: unknown[] }).business_market_links
    : [];

  return {
    version: 1,
    player_id: playerId,
    owned_lots: ownedLotsRaw
      .filter((item) => item && typeof item === 'object')
      .map((item) => {
        const tileKey = String((item as { tile_key?: unknown }).tile_key || '');
        const x = Number((item as { x?: unknown }).x || 0);
        const y = Number((item as { y?: unknown }).y || 0);
        const districtKey = (item as { district_key?: unknown }).district_key == null
          ? null
          : String((item as { district_key?: unknown }).district_key);
        const districtLabel = (item as { district_label?: unknown }).district_label == null
          ? null
          : String((item as { district_label?: unknown }).district_label);
        const zoneType = String((item as { zone_type?: unknown }).zone_type || 'service_flex') as BusinessSandboxState['owned_lots'][number]['zone_type'];
        const trafficScore = Number((item as { traffic_score?: unknown }).traffic_score || 0);
        const developmentPotential = Number((item as { development_potential?: unknown }).development_potential || 0);
        const regionId = inferRegionId(tileKey, districtKey);
        const demandScore = Number((item as { demand_score?: unknown }).demand_score || 0)
          || estimateSlotDemandScore(trafficScore, developmentPotential, regionId, zoneType);
        const purchasePriceXgp = Number((item as { purchase_price_xgp?: unknown }).purchase_price_xgp || 0);

        return {
          tile_key: tileKey,
          x,
          y,
          address: String(
            (item as { address?: unknown }).address
            || buildSlotAddress(regionId, districtLabel || tileKey, y, x),
          ),
          district_key: districtKey,
          district_label: districtLabel,
          region: inferRegionKind(regionId, (item as { region?: unknown }).region),
          zone_type: zoneType,
          size: String((item as { size?: unknown }).size || 'small') as BusinessSandboxState['owned_lots'][number]['size'],
          value_xgp: Number((item as { value_xgp?: unknown }).value_xgp || 0)
            || estimateSlotCurrentValue(purchasePriceXgp, demandScore, regionId),
          purchase_price_xgp: purchasePriceXgp,
          traffic_score: trafficScore,
          development_potential: developmentPotential,
          demand_score: demandScore,
          owner_player_id: String((item as { owner_player_id?: unknown }).owner_player_id || playerId),
          planned_business_type: (item as { planned_business_type?: unknown }).planned_business_type == null ? null : String((item as { planned_business_type?: unknown }).planned_business_type),
          linked_business_id: (item as { linked_business_id?: unknown }).linked_business_id == null
            ? ((item as { placed_business_id?: unknown }).placed_business_id == null ? null : String((item as { placed_business_id?: unknown }).placed_business_id))
            : String((item as { linked_business_id?: unknown }).linked_business_id),
          placed_business_id: (item as { placed_business_id?: unknown }).placed_business_id == null ? null : String((item as { placed_business_id?: unknown }).placed_business_id),
          development_stage: String((item as { development_stage?: unknown }).development_stage || 'land') as BusinessSandboxState['owned_lots'][number]['development_stage'],
          purchased_at: String((item as { purchased_at?: unknown }).purchased_at || new Date(0).toISOString()),
        };
      })
      .filter((item) => item.tile_key),
    business_market_links: businessLinksRaw
      .filter((item) => item && typeof item === 'object')
      .map((item) => ({
        business_id: String((item as { business_id?: unknown }).business_id || ''),
        listing_id: String((item as { listing_id?: unknown }).listing_id || ''),
        listing_name: String((item as { listing_name?: unknown }).listing_name || ''),
        tile_key: (item as { tile_key?: unknown }).tile_key == null ? null : String((item as { tile_key?: unknown }).tile_key),
        district_key: (item as { district_key?: unknown }).district_key == null ? null : String((item as { district_key?: unknown }).district_key),
        district_label: (item as { district_label?: unknown }).district_label == null ? null : String((item as { district_label?: unknown }).district_label),
        location_label: String((item as { location_label?: unknown }).location_label || 'City market'),
        growth_phase_key: String((item as { growth_phase_key?: unknown }).growth_phase_key || 'small_fruit_shop') as BusinessSandboxState['business_market_links'][number]['growth_phase_key'],
      }))
      .filter((item) => item.business_id && item.listing_id),
  };
}

export async function readBusinessSandboxState(playerId: string): Promise<BusinessSandboxState> {
  if (!playerId) return createEmptyBusinessSandboxState('');
  const raw = await AsyncStorage.getItem(BUSINESS_SANDBOX_STORAGE_KEY(playerId));
  if (!raw) return createEmptyBusinessSandboxState(playerId);

  try {
    const parsed = sanitizeState(JSON.parse(raw), playerId);
    return parsed || createEmptyBusinessSandboxState(playerId);
  } catch {
    return createEmptyBusinessSandboxState(playerId);
  }
}

export async function updateBusinessSandboxState(
  playerId: string,
  updater: (current: BusinessSandboxState) => BusinessSandboxState,
): Promise<BusinessSandboxState> {
  const current = await readBusinessSandboxState(playerId);
  const next = sanitizeState(updater(current), playerId) || createEmptyBusinessSandboxState(playerId);
  await AsyncStorage.setItem(BUSINESS_SANDBOX_STORAGE_KEY(playerId), JSON.stringify(next));
  return next;
}

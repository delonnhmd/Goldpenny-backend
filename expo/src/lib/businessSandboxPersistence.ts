import AsyncStorage from '@react-native-async-storage/async-storage';

import { createEmptyBusinessSandboxState } from '@/lib/businessSandbox';
import { createSlotEconomicRecord, getStableSlotAddress } from '@/lib/slotEconomics';
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
  if (raw.includes('market')) return 'market';
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

  const ownedLots = ownedLotsRaw
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
      const regionId = inferRegionId(tileKey, districtKey);
      const region = inferRegionKind(regionId, (item as { region?: unknown }).region);
      const purchasePriceXgp = Number((item as { purchase_price_xgp?: unknown }).purchase_price_xgp || 0);
      const linkedBusinessId = (item as { linked_business_id?: unknown }).linked_business_id == null
        ? ((item as { placed_business_id?: unknown }).placed_business_id == null ? null : String((item as { placed_business_id?: unknown }).placed_business_id))
        : String((item as { linked_business_id?: unknown }).linked_business_id);
      const plannedBusinessType = (item as { planned_business_type?: unknown }).planned_business_type == null
        ? null
        : String((item as { planned_business_type?: unknown }).planned_business_type);
      const developmentStage = String((item as { development_stage?: unknown }).development_stage || 'land') as BusinessSandboxState['owned_lots'][number]['development_stage'];
      const economicSlot = createSlotEconomicRecord({
        slot_id: tileKey,
        address: String(
          (item as { address?: unknown }).address
          || getStableSlotAddress({ slot_id: tileKey, district: districtLabel || districtKey, region }),
        ),
        region,
        district: districtLabel || districtKey || regionId,
        slot_type: zoneType,
        purchase_price: purchasePriceXgp,
        current_value: Number((item as { value_xgp?: unknown }).value_xgp || 0),
        demand_score: (item as { demand_score?: unknown }).demand_score == null ? null : Number((item as { demand_score?: unknown }).demand_score),
        foot_traffic_score: (item as { foot_traffic_score?: unknown }).foot_traffic_score == null ? null : Number((item as { foot_traffic_score?: unknown }).foot_traffic_score),
        traffic_score: (item as { traffic_score?: unknown }).traffic_score == null ? null : Number((item as { traffic_score?: unknown }).traffic_score),
        competition_score: (item as { competition_score?: unknown }).competition_score == null ? null : Number((item as { competition_score?: unknown }).competition_score),
        risk_score: (item as { risk_score?: unknown }).risk_score == null ? null : Number((item as { risk_score?: unknown }).risk_score),
        supply_access_score: (item as { supply_access_score?: unknown }).supply_access_score == null ? null : Number((item as { supply_access_score?: unknown }).supply_access_score),
        best_business_fit: (item as { best_business_fit?: unknown }).best_business_fit == null
          ? null
          : String((item as { best_business_fit?: unknown }).best_business_fit) as BusinessSandboxState['owned_lots'][number]['best_business_fit'],
        linked_business_id: linkedBusinessId,
        linked_business_type: plannedBusinessType,
        owner_player_id: String((item as { owner_player_id?: unknown }).owner_player_id || playerId),
        ownership_status: (item as { ownership_status?: unknown }).ownership_status == null
          ? `owned_${developmentStage}`
          : String((item as { ownership_status?: unknown }).ownership_status),
        development_potential: (item as { development_potential?: unknown }).development_potential == null
          ? null
          : Number((item as { development_potential?: unknown }).development_potential),
        location_business_multiplier: (item as { location_business_multiplier?: unknown }).location_business_multiplier == null
          ? null
          : Number((item as { location_business_multiplier?: unknown }).location_business_multiplier),
      });

      return {
        tile_key: tileKey,
        x,
        y,
        address: economicSlot.address,
        district_key: districtKey,
        district_label: districtLabel,
        region: region || economicSlot.district_category,
        zone_type: zoneType,
        size: String((item as { size?: unknown }).size || 'small') as BusinessSandboxState['owned_lots'][number]['size'],
        value_xgp: economicSlot.current_value,
        purchase_price_xgp: purchasePriceXgp,
        traffic_score: economicSlot.foot_traffic_score,
        foot_traffic_score: economicSlot.foot_traffic_score,
        development_potential: economicSlot.development_potential,
        demand_score: economicSlot.demand_score,
        competition_score: economicSlot.competition_score,
        risk_score: economicSlot.risk_score,
        supply_access_score: economicSlot.supply_access_score,
        best_business_fit: economicSlot.best_business_fit,
        location_business_multiplier: economicSlot.location_business_multiplier,
        owner_player_id: economicSlot.owner_player_id || playerId,
        ownership_status: economicSlot.ownership_status,
        planned_business_type: plannedBusinessType,
        linked_business_id: linkedBusinessId,
        placed_business_id: (item as { placed_business_id?: unknown }).placed_business_id == null ? null : String((item as { placed_business_id?: unknown }).placed_business_id),
        development_stage: developmentStage,
        purchased_at: String((item as { purchased_at?: unknown }).purchased_at || new Date(0).toISOString()),
      };
    })
    .filter((item) => item.tile_key);

  const ownedLotByTileKey = new Map(ownedLots.map((lot) => [lot.tile_key, lot]));
  const marketLinks = businessLinksRaw
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const tileKey = (item as { tile_key?: unknown }).tile_key == null ? null : String((item as { tile_key?: unknown }).tile_key);
      const linkedLot = tileKey ? ownedLotByTileKey.get(tileKey) || null : null;
      return {
        business_id: String((item as { business_id?: unknown }).business_id || ''),
        listing_id: String((item as { listing_id?: unknown }).listing_id || ''),
        listing_name: String((item as { listing_name?: unknown }).listing_name || ''),
        tile_key: tileKey,
        district_key: (item as { district_key?: unknown }).district_key == null ? linkedLot?.district_key || null : String((item as { district_key?: unknown }).district_key),
        district_label: (item as { district_label?: unknown }).district_label == null ? linkedLot?.district_label || null : String((item as { district_label?: unknown }).district_label),
        location_label: String((item as { location_label?: unknown }).location_label || linkedLot?.address || 'City market'),
        growth_phase_key: String((item as { growth_phase_key?: unknown }).growth_phase_key || 'small_fruit_shop') as BusinessSandboxState['business_market_links'][number]['growth_phase_key'],
        location_business_multiplier: (item as { location_business_multiplier?: unknown }).location_business_multiplier == null
          ? linkedLot?.location_business_multiplier || null
          : Number((item as { location_business_multiplier?: unknown }).location_business_multiplier),
      };
    })
    .filter((item) => item.business_id && item.listing_id);

  return {
    version: 1,
    player_id: playerId,
    owned_lots: ownedLots,
    business_market_links: marketLinks,
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

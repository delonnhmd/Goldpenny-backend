import type { SandboxMapTile } from '@/components/gameMap';
import {
  calculateSlotCurrentValue,
  createSlotEconomicRecord,
  getStableSlotAddress,
} from '@/lib/slotEconomics';
import type {
  ActiveBusinessProfile,
  BusinessFamilyKey,
  BusinessGrowthPhaseDefinition,
  BusinessGrowthPhaseKey,
  BusinessLotSize,
  BusinessMarketListing,
  BusinessSandboxState,
  BusinessTypeKey,
  PlayerBusinessRecord,
  SandboxOwnedLot,
} from '@/types/business';

const GROWTH_PHASES: BusinessGrowthPhaseDefinition[] = [
  {
    key: 'fruit_cart',
    family: 'fruit',
    label: 'Fruit Cart',
    stage: 1,
    revenueBand: 'Tiny but nimble',
    costBand: 'Very low',
    riskBand: 'Low',
    staffCapacity: 1,
    wageBaseXgp: 18,
    managementTools: ['Manual pricing', 'Route scouting'],
    unlockHint: 'Starter curbside hustle.',
  },
  {
    key: 'fruit_truck',
    family: 'fruit',
    label: 'Fruit Truck',
    stage: 2,
    revenueBand: 'Mobile neighborhood sales',
    costBand: 'Fuel + spoilage pressure',
    riskBand: 'Moderate',
    staffCapacity: 3,
    wageBaseXgp: 24,
    managementTools: ['Route planning', 'Inventory timing'],
    unlockHint: 'Needs stronger traffic and stable demand.',
  },
  {
    key: 'small_fruit_shop',
    family: 'fruit',
    label: 'Small Fruit Shop',
    stage: 3,
    revenueBand: 'Reliable storefront turnover',
    costBand: 'Rent + staffing',
    riskBand: 'Moderate',
    staffCapacity: 5,
    wageBaseXgp: 32,
    managementTools: ['Store hours', 'Supplier leverage', 'Promotions'],
    unlockHint: 'First real storefront phase.',
  },
  {
    key: 'large_fruit_store',
    family: 'fruit',
    label: 'Large Fruit Store',
    stage: 4,
    revenueBand: 'Strong local anchor',
    costBand: 'Heavy overhead',
    riskBand: 'High',
    staffCapacity: 9,
    wageBaseXgp: 40,
    managementTools: ['Shift scheduling', 'Waste controls', 'Pricing zones'],
    unlockHint: 'Requires better land and steady performance.',
  },
  {
    key: 'fruit_chain',
    family: 'fruit',
    label: 'Fruit Chain',
    stage: 5,
    revenueBand: 'Multi-site growth',
    costBand: 'Regional management',
    riskBand: 'High',
    staffCapacity: 15,
    wageBaseXgp: 48,
    managementTools: ['District expansion', 'Hiring funnels', 'Brand campaigns'],
    unlockHint: 'Scale beyond a single storefront.',
  },
  {
    key: 'fruit_corporation',
    family: 'fruit',
    label: 'Fruit Corporation',
    stage: 6,
    revenueBand: 'Citywide network',
    costBand: 'Executive overhead',
    riskBand: 'Extreme',
    staffCapacity: 26,
    wageBaseXgp: 60,
    managementTools: ['Regional ops', 'Finance stack', 'Executive staffing'],
    unlockHint: 'Late-game enterprise phase.',
  },
  {
    key: 'food_cart',
    family: 'food',
    label: 'Food Cart',
    stage: 1,
    revenueBand: 'Cheap fast service',
    costBand: 'Very low',
    riskBand: 'Low',
    staffCapacity: 2,
    wageBaseXgp: 20,
    managementTools: ['Menu pruning', 'Peak-hour timing'],
    unlockHint: 'Starter food hustle.',
  },
  {
    key: 'food_truck',
    family: 'food',
    label: 'Food Truck',
    stage: 2,
    revenueBand: 'Mobile hot-zone revenue',
    costBand: 'Fuel + ingredients',
    riskBand: 'Moderate',
    staffCapacity: 4,
    wageBaseXgp: 28,
    managementTools: ['Hotspot routing', 'Inventory prep', 'Menu mix'],
    unlockHint: 'Map-driven mobile business phase.',
  },
  {
    key: 'food_kiosk',
    family: 'food',
    label: 'Kiosk',
    stage: 3,
    revenueBand: 'Steady foot traffic',
    costBand: 'Rent + labor',
    riskBand: 'Moderate',
    staffCapacity: 6,
    wageBaseXgp: 35,
    managementTools: ['Queue management', 'Prep stations', 'Upsell mix'],
    unlockHint: 'Needs stronger foot traffic and staffing depth.',
  },
  {
    key: 'food_restaurant',
    family: 'food',
    label: 'Restaurant',
    stage: 4,
    revenueBand: 'High-ticket dining',
    costBand: 'Large payroll',
    riskBand: 'High',
    staffCapacity: 11,
    wageBaseXgp: 44,
    managementTools: ['Reservations', 'Kitchen staffing', 'Quality control'],
    unlockHint: 'Upgrade into full-service operations.',
  },
  {
    key: 'food_franchise',
    family: 'food',
    label: 'Franchise',
    stage: 5,
    revenueBand: 'Repeatable multi-unit income',
    costBand: 'Corporate process load',
    riskBand: 'High',
    staffCapacity: 18,
    wageBaseXgp: 52,
    managementTools: ['Franchise playbooks', 'Area managers', 'Brand controls'],
    unlockHint: 'Scale beyond one location.',
  },
  {
    key: 'food_corporation',
    family: 'food',
    label: 'Food Corporation',
    stage: 6,
    revenueBand: 'Metro-level dominance',
    costBand: 'Executive + legal load',
    riskBand: 'Extreme',
    staffCapacity: 30,
    wageBaseXgp: 66,
    managementTools: ['Executive teams', 'Supply contracts', 'Portfolio management'],
    unlockHint: 'Late-game food empire phase.',
  },
];

const MARKET_BLUEPRINTS: {
  id: string;
  businessType: BusinessTypeKey;
  listingName: string;
  preferredDistrict: string;
  growthPhaseKey: BusinessGrowthPhaseKey;
  priceMultiplier: number;
  demandBias: number;
  trafficBias: number;
}[] = [
  {
    id: 'fruit_heights_corner',
    businessType: 'fruit_shop',
    listingName: 'Heights Corner Fruit Shop',
    preferredDistrict: 'heights',
    growthPhaseKey: 'small_fruit_shop',
    priceMultiplier: 0.94,
    demandBias: -4,
    trafficBias: -6,
  },
  {
    id: 'fruit_exchange_anchor',
    businessType: 'fruit_shop',
    listingName: 'Exchange Produce Anchor',
    preferredDistrict: 'exchange',
    growthPhaseKey: 'small_fruit_shop',
    priceMultiplier: 1.26,
    demandBias: 12,
    trafficBias: 10,
  },
  {
    id: 'food_midtown_truck',
    businessType: 'food_truck',
    listingName: 'Midtown Food Truck Route',
    preferredDistrict: 'midtown',
    growthPhaseKey: 'food_truck',
    priceMultiplier: 1.02,
    demandBias: 6,
    trafficBias: 8,
  },
  {
    id: 'food_harbor_truck',
    businessType: 'food_truck',
    listingName: 'Harbor Shift-Change Truck',
    preferredDistrict: 'harbor',
    growthPhaseKey: 'food_truck',
    priceMultiplier: 1.14,
    demandBias: 8,
    trafficBias: 5,
  },
  {
    id: 'fruit_large_store_preview',
    businessType: 'fruit_shop',
    listingName: 'Commerce Large Fruit Store Lease',
    preferredDistrict: 'commerce',
    growthPhaseKey: 'large_fruit_store',
    priceMultiplier: 1.7,
    demandBias: 11,
    trafficBias: 9,
  },
  {
    id: 'food_kiosk_preview',
    businessType: 'food_truck',
    listingName: 'Exchange Market Kiosk',
    preferredDistrict: 'exchange',
    growthPhaseKey: 'food_kiosk',
    priceMultiplier: 1.42,
    demandBias: 9,
    trafficBias: 12,
  },
];

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function buildSlotAddress(
  regionId: string | null | undefined,
  lotLabel: string | null | undefined,
  row: number,
  col: number,
): string {
  return getStableSlotAddress({
    slot_id: `${regionId || 'unknown'}:${row}:${col}:${lotLabel || 'slot'}`,
    district: regionId,
    region: regionId,
  });
}

export function estimateSlotDemandScore(
  trafficScore: number,
  developmentPotential: number,
  regionId?: string | null,
  zoneType?: string | null,
): number {
  return createSlotEconomicRecord({
    slot_id: `${regionId || 'region'}:${zoneType || 'slot'}:${trafficScore}:${developmentPotential}`,
    district: regionId,
    region: regionId,
    slot_type: zoneType,
    purchase_price: 0,
    traffic_score: trafficScore,
    development_potential: developmentPotential,
  }).demand_score;
}

export function estimateSlotCurrentValue(
  purchasePriceXgp: number,
  demandScore: number,
  regionId?: string | null,
): number {
  return calculateSlotCurrentValue(
    createSlotEconomicRecord({
      slot_id: `${regionId || 'region'}:${purchasePriceXgp}:${demandScore}`,
      district: regionId,
      region: regionId,
      purchase_price: purchasePriceXgp,
      demand_score: demandScore,
    }),
  );
}

export function createEmptyBusinessSandboxState(playerId: string): BusinessSandboxState {
  return {
    version: 1,
    player_id: playerId,
    owned_lots: [],
    business_market_links: [],
  };
}

export function businessLabel(type: string): string {
  if (type === 'fruit_shop') return 'Fruit Shop';
  if (type === 'food_truck') return 'Food Truck';
  return String(type || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function businessFamilyForType(type: string): BusinessFamilyKey {
  return String(type || '').toLowerCase().includes('food') ? 'food' : 'fruit';
}

export function defaultGrowthPhaseForBusinessType(type: string): BusinessGrowthPhaseKey {
  return String(type || '').toLowerCase() === 'food_truck' ? 'food_truck' : 'small_fruit_shop';
}

export function describeLotSize(size: BusinessLotSize): string {
  if (size === 'large') return 'Large';
  if (size === 'medium') return 'Medium';
  if (size === 'small') return 'Small';
  return 'Micro';
}

export function describeZoneType(zoneType: string): string {
  return String(zoneType || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function getGrowthPhase(key: BusinessGrowthPhaseKey): BusinessGrowthPhaseDefinition {
  return GROWTH_PHASES.find((phase) => phase.key === key) || GROWTH_PHASES[0];
}

export function getGrowthLadder(family: BusinessFamilyKey): BusinessGrowthPhaseDefinition[] {
  return GROWTH_PHASES.filter((phase) => phase.family === family).sort((left, right) => left.stage - right.stage);
}

export function getNextGrowthPhase(key: BusinessGrowthPhaseKey): BusinessGrowthPhaseDefinition | null {
  const phase = getGrowthPhase(key);
  return getGrowthLadder(phase.family).find((item) => item.stage === phase.stage + 1) || null;
}

function pickTileForDistrict(tiles: SandboxMapTile[], districtKey: string, usedKeys: Set<string>): SandboxMapTile | null {
  const candidates = tiles
    .filter((tile) => (
      tile.buildable
      && tile.districtKey === districtKey
      && tile.landProfile
      && !usedKeys.has(tile.key)
    ))
    .sort((left, right) => (
      (Number(right.landProfile?.trafficScore || 0) + Number(right.landProfile?.developmentPotential || 0))
      - (Number(left.landProfile?.trafficScore || 0) + Number(left.landProfile?.developmentPotential || 0))
    ));
  return candidates[0] || null;
}

function listingCompareNote(listing: Pick<BusinessMarketListing, 'demand_score' | 'traffic_potential' | 'performance_score'>): string {
  if (listing.traffic_potential >= 80) return 'Top traffic lane with strong walk-up potential.';
  if (listing.demand_score >= 78) return 'Demand-heavy listing with faster payback potential.';
  if (listing.performance_score >= 72) return 'Balanced listing with solid staffing and margin stability.';
  return 'Cheaper entry point with weaker location strength.';
}

export function deriveBusinessMarketListings(options: {
  tiles: SandboxMapTile[];
  starterOptions: { business_type: BusinessTypeKey | string; label: string; cost_xgp: number }[];
  activeBusiness: PlayerBusinessRecord | null;
}): BusinessMarketListing[] {
  const starterCostByType = new Map(
    options.starterOptions.map((item) => [String(item.business_type), Number(item.cost_xgp || 0)]),
  );
  const usedTileKeys = new Set<string>();

  return MARKET_BLUEPRINTS.map((blueprint) => {
    const tile = pickTileForDistrict(options.tiles, blueprint.preferredDistrict, usedTileKeys);
    if (tile) usedTileKeys.add(tile.key);
    const land = tile?.landProfile;
    const phase = getGrowthPhase(blueprint.growthPhaseKey);
    const baseCost = starterCostByType.get(blueprint.businessType) || (blueprint.businessType === 'food_truck' ? 1200 : 500);
    const buyableStarterPhase = defaultGrowthPhaseForBusinessType(blueprint.businessType);
    const locked = phase.stage > getGrowthPhase(buyableStarterPhase).stage;
    const price = locked
      ? Math.round(
        (baseCost * blueprint.priceMultiplier)
        + Number(land?.valueXgp || 180) * 0.62
        + (phase.stage * 95),
      )
      : Math.round(baseCost);
    const trafficPotential = clamp(Math.round(Number(land?.trafficScore || 50) + blueprint.trafficBias), 20, 100);
    const demandScore = clamp(Math.round(((trafficPotential * 0.62) + Number(land?.developmentPotential || 50) * 0.28) + blueprint.demandBias), 18, 100);
    const reputationScore = clamp(50 + (phase.stage * 7) + Math.round(blueprint.priceMultiplier * 4), 25, 100);
    const performanceScore = clamp(Math.round((demandScore + trafficPotential + reputationScore) / 3), 20, 100);
    const employees = clamp(Math.round(phase.staffCapacity * (locked ? 0.76 : 0.62)), 1, phase.staffCapacity);
    const openSlots = Math.max(0, phase.staffCapacity - employees);

    return {
      listing_id: blueprint.id,
      business_type: blueprint.businessType,
      business_family: phase.family,
      listing_name: blueprint.listingName,
      price_xgp: price,
      location_label: tile?.districtLabel ? `${tile.districtLabel} (${tile.x},${tile.y})` : 'City market',
      district_key: tile?.districtKey || blueprint.preferredDistrict,
      district_label: tile?.districtLabel || null,
      tile_key: tile?.key || null,
      tile_x: tile?.x ?? null,
      tile_y: tile?.y ?? null,
      growth_phase_key: phase.key,
      growth_phase_label: phase.label,
      employees,
      employee_capacity: phase.staffCapacity,
      open_slots: openSlots,
      wage_cost_xgp: Math.round(employees * phase.wageBaseXgp),
      performance_score: performanceScore,
      demand_score: demandScore,
      reputation_score: reputationScore,
      traffic_potential: trafficPotential,
      locked,
      lock_reason: locked ? `Grow a ${businessLabel(blueprint.businessType)} into the ${phase.label} phase first.` : null,
      management_tools: phase.managementTools,
      buyable: !locked && !options.activeBusiness,
      compare_note: listingCompareNote({
        demand_score: demandScore,
        traffic_potential: trafficPotential,
        performance_score: performanceScore,
      }),
    };
  });
}

function linkedLotForBusiness(state: BusinessSandboxState, businessId: string): SandboxOwnedLot | null {
  return state.owned_lots.find(
    (lot) => lot.linked_business_id === businessId || lot.placed_business_id === businessId,
  ) || null;
}

function marketLinkForBusiness(state: BusinessSandboxState, businessId: string) {
  return state.business_market_links.find((item) => item.business_id === businessId) || null;
}

export function deriveActiveBusinessProfile(options: {
  activeBusiness: PlayerBusinessRecord | null;
  sandboxState: BusinessSandboxState;
  latestProfitXgp: number;
  trailingProfitXgp: number;
  dayNumber: number;
}): ActiveBusinessProfile | null {
  const activeBusiness = options.activeBusiness;
  if (!activeBusiness) return null;

  const family = businessFamilyForType(activeBusiness.business_type);
  const linkedLot = linkedLotForBusiness(options.sandboxState, activeBusiness.business_id);
  const marketLink = marketLinkForBusiness(options.sandboxState, activeBusiness.business_id);
  const linkedLotEconomics = linkedLot ? createSlotEconomicRecord({
    slot_id: linkedLot.tile_key,
    address: linkedLot.address,
    region: linkedLot.region,
    district: linkedLot.district_label || linkedLot.district_key,
    slot_type: linkedLot.zone_type,
    purchase_price: linkedLot.purchase_price_xgp,
    current_value: linkedLot.value_xgp,
    demand_score: linkedLot.demand_score,
    foot_traffic_score: linkedLot.foot_traffic_score || linkedLot.traffic_score,
    traffic_score: linkedLot.traffic_score,
    competition_score: linkedLot.competition_score,
    risk_score: linkedLot.risk_score,
    supply_access_score: linkedLot.supply_access_score,
    best_business_fit: linkedLot.best_business_fit,
    linked_business_id: linkedLot.linked_business_id || linkedLot.placed_business_id,
    linked_business_type: linkedLot.planned_business_type,
    owner_player_id: linkedLot.owner_player_id,
    ownership_status: linkedLot.ownership_status,
    development_potential: linkedLot.development_potential,
    location_business_multiplier: linkedLot.location_business_multiplier,
  }) : null;
  const phaseKey = (linkedLot?.development_stage === 'built' && marketLink?.growth_phase_key)
    ? marketLink.growth_phase_key
    : (marketLink?.growth_phase_key || defaultGrowthPhaseForBusinessType(activeBusiness.business_type));
  const phase = getGrowthPhase(phaseKey);
  const nextPhase = getNextGrowthPhase(phase.key);
  const trafficScore = clamp(
    Number(linkedLotEconomics?.foot_traffic_score || linkedLot?.traffic_score || 58)
      + (marketLink?.district_key === 'exchange' ? 8 : 0)
      + (marketLink?.district_key === 'harbor' ? 4 : 0),
    20,
    100,
  );
  const demandScore = clamp(
    Math.round(
      (Number(linkedLotEconomics?.demand_score || linkedLot?.demand_score || 60) * 0.72)
      + (trafficScore * 0.18)
      + options.dayNumber
      + ((Number(linkedLotEconomics?.location_business_multiplier || marketLink?.location_business_multiplier || 1) - 1) * 18),
    ),
    25,
    100,
  );
  const performanceScore = clamp(
    Math.round(
      42
      + (Number(activeBusiness.reputation || 0) * 0.35)
      + (Number(options.latestProfitXgp || 0) / 8)
      + (Number(options.trailingProfitXgp || 0) / 28),
    ),
    18,
    100,
  );
  const employeeCapacity = phase.staffCapacity + (linkedLot?.size === 'large' ? 2 : linkedLot?.size === 'medium' ? 1 : 0);
  const fillRatio = clamp(0.52 + (demandScore / 220), 0.4, 0.94);
  const employees = clamp(Math.round(employeeCapacity * fillRatio), 1, employeeCapacity);
  const realPlayerShare = clamp((options.dayNumber - 3) / 20, 0, 0.58);
  const playerEmployees = clamp(Math.round(employees * realPlayerShare), 0, Math.max(0, employees - 1));
  const npcEmployees = Math.max(0, employees - playerEmployees);
  const locationLabel = linkedLot
    ? linkedLotEconomics?.address || linkedLot.address || `${linkedLot.district_label || 'Owned lot'} (${linkedLot.x},${linkedLot.y})`
    : marketLink?.location_label || (activeBusiness.region_key ? `${activeBusiness.region_key} market` : 'City market');

  return {
    business_id: activeBusiness.business_id,
    business_type: activeBusiness.business_type,
    business_family: family,
    display_name: activeBusiness.business_name || marketLink?.listing_name || businessLabel(activeBusiness.business_type),
    growth_phase_key: phase.key,
    growth_phase_label: phase.label,
    next_phase_key: nextPhase?.key || null,
    next_phase_label: nextPhase?.label || null,
    employees,
    npc_employees: npcEmployees,
    player_employees: playerEmployees,
    employee_capacity: employeeCapacity,
    open_slots: Math.max(0, employeeCapacity - employees),
    wage_cost_xgp: Math.round(employees * phase.wageBaseXgp * (1 + (Number(activeBusiness.reputation || 0) / 260))),
    performance_score: performanceScore,
    demand_score: demandScore,
    reputation_score: clamp(Number(activeBusiness.reputation || 0), 0, 100),
    traffic_score: trafficScore,
    risk_band: phase.riskBand,
    management_tools: phase.managementTools,
    location_label: locationLabel,
    district_key: linkedLot?.district_key || marketLink?.district_key || activeBusiness.region_key || null,
    district_label: linkedLot?.district_label || marketLink?.district_label || null,
    tile_key: linkedLot?.tile_key || marketLink?.tile_key || null,
    location_business_multiplier: marketLink?.location_business_multiplier ?? linkedLotEconomics?.location_business_multiplier ?? null,
    phase_progress_label: nextPhase
      ? `Next: ${nextPhase.label}`
      : 'Top phase reached',
  };
}

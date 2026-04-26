export type SlotBusinessFit = 'fruit_shop' | 'food_truck' | 'either';
export type SlotDistrictCategory = 'downtown' | 'suburban' | 'market' | 'industrial' | 'default';
export type SlotPrimaryActionKey = 'buy_slot' | 'open_business' | 'manage_operate_business';
export type SlotBottomSheetActionKey = SlotPrimaryActionKey | 'inspect';

export interface SlotEconomicInput {
  slot_id: string;
  address?: string | null;
  region?: string | null;
  district?: string | null;
  slot_type?: string | null;
  purchase_price: number;
  current_value?: number | null;
  demand_score?: number | null;
  foot_traffic_score?: number | null;
  traffic_score?: number | null;
  competition_score?: number | null;
  risk_score?: number | null;
  supply_access_score?: number | null;
  best_business_fit?: SlotBusinessFit | null;
  linked_business_id?: string | null;
  linked_business_type?: string | null;
  owner_player_id?: string | null;
  ownership_status?: string | null;
  development_potential?: number | null;
  location_business_multiplier?: number | null;
}

export interface SlotEconomicRecord {
  slot_id: string;
  address: string;
  region: string | null;
  district: string | null;
  district_category: SlotDistrictCategory;
  slot_type: string | null;
  purchase_price: number;
  current_value: number;
  demand_score: number;
  foot_traffic_score: number;
  competition_score: number;
  risk_score: number;
  supply_access_score: number;
  best_business_fit: SlotBusinessFit;
  linked_business_id: string | null;
  linked_business_type: string | null;
  owner_player_id: string | null;
  ownership_status: string;
  development_potential: number;
  location_business_multiplier: number;
}

export interface SlotRevenuePreview {
  business_type: 'fruit_shop' | 'food_truck';
  location_multiplier: number;
  expected_revenue: number;
  low_revenue: number;
  high_revenue: number;
}

export interface SlotBottomSheetButtonState {
  key: SlotBottomSheetActionKey;
  label: string;
}

export interface SlotBottomSheetState {
  primary_action: SlotPrimaryActionKey;
  primary_label: string;
  buttons: SlotBottomSheetButtonState[];
}

export interface SlotBusinessBadgeState {
  show_badge: boolean;
  label: string | null;
  tone: 'default' | 'owned' | 'built';
}

const DISTRICT_DEFAULTS: Record<SlotDistrictCategory, {
  demand: number;
  footTraffic: number;
  competition: number;
  risk: number;
  supply: number;
  bestFit: SlotBusinessFit;
}> = {
  downtown: {
    demand: 78,
    footTraffic: 84,
    competition: 72,
    risk: 62,
    supply: 66,
    bestFit: 'food_truck',
  },
  suburban: {
    demand: 58,
    footTraffic: 54,
    competition: 34,
    risk: 24,
    supply: 78,
    bestFit: 'fruit_shop',
  },
  market: {
    demand: 82,
    footTraffic: 78,
    competition: 76,
    risk: 46,
    supply: 82,
    bestFit: 'either',
  },
  industrial: {
    demand: 42,
    footTraffic: 48,
    competition: 32,
    risk: 38,
    supply: 88,
    bestFit: 'food_truck',
  },
  default: {
    demand: 55,
    footTraffic: 55,
    competition: 45,
    risk: 36,
    supply: 60,
    bestFit: 'either',
  },
};

const DISTRICT_GROWTH_MODIFIERS: Record<SlotDistrictCategory, number> = {
  downtown: 0.12,
  market: 0.10,
  industrial: 0.08,
  suburban: 0.05,
  default: 0.03,
};

const ADDRESS_POOLS: Record<Exclude<SlotDistrictCategory, 'default'>, string[]> = {
  downtown: [
    '1203 Market Line Ave',
    '88 Riverfront Plaza',
    '410 Central Trade St',
    '726 Commerce Row',
    '51 Skyline Market Blvd',
  ],
  suburban: [
    '240 Oak Garden Ln',
    '715 Greenfield Way',
    '332 Maple Creek Dr',
    '909 Willow Bend Rd',
    '128 Pine Orchard St',
  ],
  market: [
    '200 Vendor Square',
    '415 Fresh Market St',
    '909 Orchard Plaza',
    '77 Trade Corner',
  ],
  industrial: [
    '600 Foundry Loop',
    '144 Warehouse Park Dr',
    '915 Rail Yard Ave',
  ],
};

const SLOT_TYPE_BONUSES: Record<string, {
  demand: number;
  traffic: number;
  competition: number;
  risk: number;
  supply: number;
}> = {
  commercial_core: { demand: 8, traffic: 6, competition: 8, risk: 4, supply: 2 },
  mixed_use: { demand: 5, traffic: 4, competition: 3, risk: 2, supply: 4 },
  service_flex: { demand: 2, traffic: 3, competition: 1, risk: 1, supply: 8 },
  logistics: { demand: -4, traffic: 1, competition: -4, risk: 2, supply: 12 },
  residential_edge: { demand: 3, traffic: -2, competition: -5, risk: -6, supply: 6 },
};

const BASE_REVENUE_BY_BUSINESS_TYPE: Record<'fruit_shop' | 'food_truck', number> = {
  fruit_shop: 120,
  food_truck: 180,
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function roundMoney(value: number): number {
  return Math.round(Number(value || 0) * 100) / 100;
}

function stableHash(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
}

function normalizeFinite(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function titleCase(value: string): string {
  return value
    .split(' ')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function zoneBonus(slotType: string | null | undefined) {
  return SLOT_TYPE_BONUSES[String(slotType || '').trim().toLowerCase()] || {
    demand: 0,
    traffic: 0,
    competition: 0,
    risk: 0,
    supply: 0,
  };
}

export function normalizeSlotDistrictCategory(...values: Array<string | null | undefined>): SlotDistrictCategory {
  const combined = values
    .map((value) => String(value || '').trim().toLowerCase())
    .filter(Boolean)
    .join(' ');
  if (!combined) return 'default';
  if (combined.includes('market')) return 'market';
  if (
    combined.includes('industrial')
    || combined.includes('harbor')
    || combined.includes('warehouse')
    || combined.includes('rail')
  ) {
    return 'industrial';
  }
  if (
    combined.includes('downtown')
    || combined.includes('exchange')
    || combined.includes('central')
    || combined.includes('commerce')
  ) {
    return 'downtown';
  }
  if (
    combined.includes('suburban')
    || combined.includes('brookside')
    || combined.includes('riverside')
    || combined.includes('river')
    || combined.includes('oak')
    || combined.includes('willow')
  ) {
    return 'suburban';
  }
  return 'default';
}

export function getStableSlotAddress(input: Pick<SlotEconomicInput, 'slot_id' | 'district' | 'region'>): string {
  const category = normalizeSlotDistrictCategory(input.district, input.region);
  const pool = ADDRESS_POOLS[category === 'default' ? 'suburban' : category];
  const seed = stableHash(`${category}:${String(input.slot_id || 'slot')}`);
  return pool[seed % pool.length];
}

function inferFootTrafficScore(input: SlotEconomicInput, category: SlotDistrictCategory): number {
  if (input.foot_traffic_score != null) {
    return clamp(Math.round(normalizeFinite(input.foot_traffic_score)), 0, 100);
  }
  const trafficSeed = normalizeFinite(input.traffic_score, DISTRICT_DEFAULTS[category].footTraffic);
  const computed = (DISTRICT_DEFAULTS[category].footTraffic * 0.42) + (trafficSeed * 0.58) + zoneBonus(input.slot_type).traffic;
  return clamp(Math.round(computed), 0, 100);
}

function inferDemandScore(
  input: SlotEconomicInput,
  category: SlotDistrictCategory,
  footTrafficScore: number,
): number {
  if (input.demand_score != null) {
    return clamp(Math.round(normalizeFinite(input.demand_score)), 0, 100);
  }
  const developmentPotential = normalizeFinite(input.development_potential, DISTRICT_DEFAULTS[category].demand);
  const computed = (
    (DISTRICT_DEFAULTS[category].demand * 0.38)
    + (developmentPotential * 0.34)
    + (footTrafficScore * 0.28)
    + zoneBonus(input.slot_type).demand
  );
  return clamp(Math.round(computed), 0, 100);
}

function inferCompetitionScore(
  input: SlotEconomicInput,
  category: SlotDistrictCategory,
  demandScore: number,
  footTrafficScore: number,
): number {
  if (input.competition_score != null) {
    return clamp(Math.round(normalizeFinite(input.competition_score)), 0, 100);
  }
  const computed = (
    (DISTRICT_DEFAULTS[category].competition * 0.62)
    + (footTrafficScore * 0.2)
    + (demandScore * 0.18)
    + zoneBonus(input.slot_type).competition
  );
  return clamp(Math.round(computed), 0, 100);
}

function inferRiskScore(
  input: SlotEconomicInput,
  category: SlotDistrictCategory,
  competitionScore: number,
  footTrafficScore: number,
): number {
  if (input.risk_score != null) {
    return clamp(Math.round(normalizeFinite(input.risk_score)), 0, 100);
  }
  const computed = (
    (DISTRICT_DEFAULTS[category].risk * 0.72)
    + (competitionScore * 0.16)
    + (Math.max(0, footTrafficScore - 50) * 0.12)
    + zoneBonus(input.slot_type).risk
  );
  return clamp(Math.round(computed), 0, 100);
}

function inferSupplyAccessScore(
  input: SlotEconomicInput,
  category: SlotDistrictCategory,
): number {
  if (input.supply_access_score != null) {
    return clamp(Math.round(normalizeFinite(input.supply_access_score)), 0, 100);
  }
  const developmentPotential = normalizeFinite(input.development_potential, DISTRICT_DEFAULTS[category].supply);
  const computed = (
    (DISTRICT_DEFAULTS[category].supply * 0.66)
    + (developmentPotential * 0.12)
    + zoneBonus(input.slot_type).supply
  );
  return clamp(Math.round(computed), 0, 100);
}

function inferBestBusinessFit(input: SlotEconomicInput, category: SlotDistrictCategory): SlotBusinessFit {
  if (input.best_business_fit === 'fruit_shop' || input.best_business_fit === 'food_truck' || input.best_business_fit === 'either') {
    return input.best_business_fit;
  }
  const slotType = String(input.slot_type || '').trim().toLowerCase();
  if (category === 'market') return 'either';
  if (category === 'industrial') return 'food_truck';
  if (category === 'downtown') return slotType === 'commercial_core' ? 'food_truck' : 'either';
  if (category === 'suburban') return slotType === 'logistics' ? 'food_truck' : 'fruit_shop';
  return DISTRICT_DEFAULTS[category].bestFit;
}

export function calculateSlotCurrentValue(slot: Pick<SlotEconomicRecord, 'purchase_price' | 'demand_score' | 'foot_traffic_score' | 'risk_score' | 'district_category'>): number {
  const purchasePrice = Math.max(0, normalizeFinite(slot.purchase_price, 0));
  if (!purchasePrice) return 0;
  const demandModifier = (normalizeFinite(slot.demand_score, 0) - 50) / 250;
  const trafficModifier = (normalizeFinite(slot.foot_traffic_score, 0) - 50) / 300;
  const riskModifier = normalizeFinite(slot.risk_score, 0) / 500;
  const districtGrowthModifier = DISTRICT_GROWTH_MODIFIERS[slot.district_category] ?? DISTRICT_GROWTH_MODIFIERS.default;
  const rawValue = purchasePrice * (1 + demandModifier + trafficModifier - riskModifier + districtGrowthModifier);
  const clamped = clamp(rawValue, purchasePrice * 0.75, purchasePrice * 1.75);
  return roundMoney(clamped);
}

export function calculateSlotLocationBusinessMultiplier(slot: Pick<SlotEconomicRecord, 'demand_score' | 'foot_traffic_score' | 'competition_score' | 'risk_score'>): number {
  const multiplier = 1
    + ((normalizeFinite(slot.demand_score, 0) - 50) / 250)
    + ((normalizeFinite(slot.foot_traffic_score, 0) - 50) / 220)
    - ((normalizeFinite(slot.competition_score, 0) - 50) / 250)
    - ((normalizeFinite(slot.risk_score, 0) - 50) / 350);
  return roundMoney(clamp(multiplier, 0.65, 1.5));
}

export function createSlotEconomicRecord(input: SlotEconomicInput): SlotEconomicRecord {
  const category = normalizeSlotDistrictCategory(input.district, input.region);
  const footTrafficScore = inferFootTrafficScore(input, category);
  const demandScore = inferDemandScore(input, category, footTrafficScore);
  const competitionScore = inferCompetitionScore(input, category, demandScore, footTrafficScore);
  const riskScore = inferRiskScore(input, category, competitionScore, footTrafficScore);
  const supplyAccessScore = inferSupplyAccessScore(input, category);
  const record: SlotEconomicRecord = {
    slot_id: String(input.slot_id || '').trim(),
    address: String(input.address || '').trim() || getStableSlotAddress(input),
    region: String(input.region || '').trim() || null,
    district: String(input.district || '').trim() || null,
    district_category: category,
    slot_type: String(input.slot_type || '').trim() || null,
    purchase_price: roundMoney(normalizeFinite(input.purchase_price, 0)),
    current_value: 0,
    demand_score: demandScore,
    foot_traffic_score: footTrafficScore,
    competition_score: competitionScore,
    risk_score: riskScore,
    supply_access_score: supplyAccessScore,
    best_business_fit: inferBestBusinessFit(input, category),
    linked_business_id: String(input.linked_business_id || '').trim() || null,
    linked_business_type: String(input.linked_business_type || '').trim() || null,
    owner_player_id: String(input.owner_player_id || '').trim() || null,
    ownership_status: String(input.ownership_status || '').trim() || (
      input.owner_player_id
        ? (input.linked_business_id ? 'owned_built' : 'owned')
        : 'unowned'
    ),
    development_potential: clamp(Math.round(normalizeFinite(input.development_potential, DISTRICT_DEFAULTS[category].demand)), 0, 100),
    location_business_multiplier: 0,
  };
  record.current_value = calculateSlotCurrentValue(record);
  record.location_business_multiplier = input.location_business_multiplier != null
    ? roundMoney(clamp(normalizeFinite(input.location_business_multiplier, 1), 0.65, 1.5))
    : calculateSlotLocationBusinessMultiplier(record);
  return record;
}

export function calculateSlotRevenuePreview(
  slotInput: SlotEconomicRecord | SlotEconomicInput,
  businessType: 'fruit_shop' | 'food_truck',
): SlotRevenuePreview {
  const slot = 'district_category' in slotInput
    ? slotInput
    : createSlotEconomicRecord(slotInput);
  const baseRevenue = BASE_REVENUE_BY_BUSINESS_TYPE[businessType];
  const locationMultiplier = clamp(
    1
      + ((slot.demand_score - 50) / 200)
      + ((slot.foot_traffic_score - 50) / 180)
      - ((slot.competition_score - 50) / 220)
      - ((slot.risk_score - 50) / 300)
      + ((slot.supply_access_score - 50) / 250),
    0.55,
    1.75,
  );
  const expectedRevenue = roundMoney(baseRevenue * locationMultiplier);
  return {
    business_type: businessType,
    location_multiplier: roundMoney(locationMultiplier),
    expected_revenue: expectedRevenue,
    low_revenue: roundMoney(expectedRevenue * 0.75),
    high_revenue: roundMoney(expectedRevenue * 1.25),
  };
}

export function isHotSlot(slotInput: SlotEconomicRecord | SlotEconomicInput): boolean {
  const slot = 'district_category' in slotInput
    ? slotInput
    : createSlotEconomicRecord(slotInput);
  return slot.demand_score >= 78 && slot.foot_traffic_score >= 78;
}

export function getSlotBusinessBadgeState(slotInput: Pick<SlotEconomicInput, 'linked_business_id' | 'linked_business_type' | 'owner_player_id'>): SlotBusinessBadgeState {
  const linkedBusinessType = String(slotInput.linked_business_type || '').trim();
  const linkedBusinessId = String(slotInput.linked_business_id || '').trim();
  if (linkedBusinessId) {
    const label = linkedBusinessType
      ? titleCase(linkedBusinessType.replace(/_/g, ' '))
      : 'Business linked';
    return {
      show_badge: true,
      label,
      tone: 'built',
    };
  }
  if (String(slotInput.owner_player_id || '').trim()) {
    return {
      show_badge: true,
      label: 'Owned',
      tone: 'owned',
    };
  }
  return {
    show_badge: false,
    label: null,
    tone: 'default',
  };
}

export function getSlotBottomSheetState(options: {
  is_owned: boolean;
  has_linked_business: boolean;
}): SlotBottomSheetState {
  const primary: SlotBottomSheetButtonState = !options.is_owned
    ? { key: 'buy_slot', label: 'Buy Slot' }
    : options.has_linked_business
      ? { key: 'manage_operate_business', label: 'Manage / Operate Business' }
      : { key: 'open_business', label: 'Open Business' };

  return {
    primary_action: primary.key as SlotPrimaryActionKey,
    primary_label: primary.label,
    buttons: [
      primary,
      { key: 'inspect', label: 'Inspect' },
    ],
  };
}

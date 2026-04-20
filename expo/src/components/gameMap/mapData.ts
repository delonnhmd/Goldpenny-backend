import type { TravelOptionSnapshot } from '@/types/gameplay';
import type { BusinessLandZoneType, BusinessLotSize } from '@/types/business';
import { theme } from '@/design/theme';

export interface MapNode {
  key: string;
  label: string;
  region: 'Suburban' | 'Downtown' | string;
  node_type: string;
  opportunity_tier: string;
  is_current_location: boolean;
}

export type SandboxTileKind =
  | 'empty_lot'
  | 'road'
  | 'building_slot'
  | 'existing_business'
  | 'service_building'
  | 'expansion_node';

export type MapTileActionTag =
  | 'meal_breakfast'
  | 'meal_lunch'
  | 'meal_dinner'
  | 'job_board'
  | 'work_shift'
  | 'rideshare'
  | 'recovery'
  | 'business_open'
  | 'business_operate'
  | 'business_inventory';

export type RoadAxis = 'horizontal' | 'vertical' | 'intersection' | null;

export interface SandboxLandProfile {
  zoneType: BusinessLandZoneType;
  size: BusinessLotSize;
  valueXgp: number;
  trafficScore: number;
  developmentPotential: number;
}

export interface SandboxDistrict {
  key: string;
  label: string;
  subtitle: string;
  tone: 'suburban' | 'downtown' | 'commercial';
  x: number;
  y: number;
  width: number;
  height: number;
  fill: string;
  accent: string;
}

export interface SandboxMapTile {
  key: string;
  x: number;
  y: number;
  kind: SandboxTileKind;
  label: string;
  shortLabel?: string;
  description: string;
  districtKey?: string | null;
  districtLabel?: string | null;
  buildable: boolean;
  selectable: boolean;
  nodeKey?: string | null;
  nodeType?: string | null;
  opportunityTier?: string | null;
  isCurrentLocation: boolean;
  roadAxis: RoadAxis;
  travelOption?: TravelOptionSnapshot | null;
  actionTags: MapTileActionTag[];
  landProfile?: SandboxLandProfile | null;
}

export interface SandboxCityMap {
  columns: number;
  rows: number;
  tileSize: number;
  worldWidth: number;
  worldHeight: number;
  districts: SandboxDistrict[];
  tiles: SandboxMapTile[];
  tileByKey: Record<string, SandboxMapTile>;
  tileByCoordinate: Record<string, SandboxMapTile>;
  tileByNodeKey: Record<string, SandboxMapTile>;
  currentLocationTileKey: string | null;
}

interface TileSeed {
  x: number;
  y: number;
  kind: SandboxTileKind;
  label: string;
  shortLabel?: string;
  description: string;
  buildable?: boolean;
  districtKey?: string | null;
  districtLabel?: string | null;
  nodeKey?: string | null;
  nodeType?: string | null;
  opportunityTier?: string | null;
  actionTags?: MapTileActionTag[];
}

export const MAP_COLUMNS = 30;
export const MAP_ROWS = 22;
// Step 96N — bumped from 28 to 32 for better mobile touch targets while still
// fine-grained enough for lot-slot precision at close zoom.
export const MAP_TILE_SIZE = 32;

const DISTRICTS: SandboxDistrict[] = [
  {
    key: 'heights',
    label: 'Heights',
    subtitle: 'Starter homes + daily needs',
    tone: 'suburban',
    x: 1,
    y: 1,
    width: 8,
    height: 7,
    fill: theme.gameUi.district.suburban.base,
    accent: theme.gameUi.district.suburban.accent,
  },
  {
    key: 'midtown',
    label: 'Midtown',
    subtitle: 'Service traffic + fast turnover',
    tone: 'downtown',
    x: 11,
    y: 1,
    width: 8,
    height: 7,
    fill: theme.gameUi.district.downtown.base,
    accent: theme.gameUi.district.downtown.highlight,
  },
  {
    key: 'exchange',
    label: 'Exchange',
    subtitle: 'Commercial demand belt',
    tone: 'commercial',
    x: 21,
    y: 1,
    width: 8,
    height: 7,
    fill: theme.gameUi.district.commercial.base,
    accent: theme.gameUi.district.commercial.accent,
  },
  {
    key: 'makers',
    label: 'Makers Row',
    subtitle: 'Small lots + light logistics',
    tone: 'suburban',
    x: 1,
    y: 14,
    width: 8,
    height: 7,
    fill: theme.gameUi.district.suburban.base,
    accent: theme.gameUi.district.suburban.accent,
  },
  {
    key: 'commerce',
    label: 'Commerce',
    subtitle: 'Dense work nodes + offices',
    tone: 'downtown',
    x: 11,
    y: 14,
    width: 8,
    height: 7,
    fill: theme.gameUi.district.downtown.accent,
    accent: theme.gameUi.district.downtown.highlight,
  },
  {
    key: 'harbor',
    label: 'Harbor',
    subtitle: 'Higher-capacity expansion land',
    tone: 'commercial',
    x: 21,
    y: 14,
    width: 8,
    height: 7,
    fill: theme.gameUi.district.commercial.base,
    accent: theme.gameUi.district.commercial.accent,
  },
];

const STATIC_SPECIAL_TILES: TileSeed[] = [
  {
    x: 23,
    y: 16,
    kind: 'service_building',
    label: 'Food Truck Court',
    shortLabel: 'DIN',
    description: 'Dinner hotspot for restaurant and food truck spending.',
    actionTags: ['meal_dinner'],
  },
  {
    x: 14,
    y: 16,
    kind: 'service_building',
    label: 'Pocket Park',
    shortLabel: 'REST',
    description: 'Leisure pocket for timed recovery and low-pressure downtime.',
    actionTags: ['recovery'],
  },
  {
    x: 27,
    y: 2,
    kind: 'expansion_node',
    label: 'North Expansion',
    shortLabel: 'EXP',
    description: 'Future district unlock node for larger projects.',
  },
  {
    x: 2,
    y: 19,
    kind: 'expansion_node',
    label: 'West Expansion',
    shortLabel: 'EXP',
    description: 'Reserved edge tile for future neighborhood growth.',
  },
  {
    x: 27,
    y: 19,
    kind: 'expansion_node',
    label: 'South Expansion',
    shortLabel: 'EXP',
    description: 'Future harbor-side buildout anchor.',
  },
];

const FIXED_NODE_ANCHORS: Record<string, { x: number; y: number }> = {
  home: { x: 4, y: 17 },
  grocery: { x: 6, y: 3 },
  rideshare_hotspot_suburban: { x: 7, y: 18 },
  job_center: { x: 15, y: 4 },
  work: { x: 16, y: 17 },
  rideshare_hotspot_downtown: { x: 13, y: 4 },
  business_spot: { x: 25, y: 17 },
  bank: { x: 22, y: 4 },
  stock_center: { x: 26, y: 3 },
  certification_school: { x: 17, y: 3 },
  housing: { x: 3, y: 15 },
  clinic: { x: 7, y: 15 },
  gas_station: { x: 5, y: 20 },
  car_sale: { x: 24, y: 2 },
};

const FLEX_NODE_ANCHORS = [
  { x: 23, y: 3 },
  { x: 24, y: 17 },
  { x: 6, y: 17 },
  { x: 15, y: 3 },
  { x: 12, y: 17 },
];

function coordinateKey(x: number, y: number): string {
  return `${x}:${y}`;
}

function tileKey(x: number, y: number): string {
  return `tile_${x}_${y}`;
}

function findDistrict(x: number, y: number): SandboxDistrict | undefined {
  return DISTRICTS.find((district) => (
    x >= district.x
    && x < district.x + district.width
    && y >= district.y
    && y < district.y + district.height
  ));
}

function isRoadTile(x: number, y: number): boolean {
  const horizontalBand = (y >= 8 && y <= 9) || (y >= 12 && y <= 13);
  const verticalBand = (x >= 9 && x <= 10) || (x >= 19 && x <= 20);
  return horizontalBand || verticalBand;
}

function roadAxisForTile(x: number, y: number): RoadAxis {
  const horizontalBand = (y >= 8 && y <= 9) || (y >= 12 && y <= 13);
  const verticalBand = (x >= 9 && x <= 10) || (x >= 19 && x <= 20);
  if (horizontalBand && verticalBand) return 'intersection';
  if (horizontalBand) return 'horizontal';
  if (verticalBand) return 'vertical';
  return null;
}

function isFrontageTile(x: number, y: number): boolean {
  return (
    y === 7
    || y === 14
    || x === 8
    || x === 11
    || x === 18
    || x === 21
  );
}

function zoneTypeForDistrict(districtKey: string | null | undefined): BusinessLandZoneType {
  switch (districtKey) {
    case 'heights':
      return 'residential_edge';
    case 'midtown':
      return 'mixed_use';
    case 'exchange':
      return 'commercial_core';
    case 'makers':
      return 'service_flex';
    case 'commerce':
      return 'mixed_use';
    case 'harbor':
      return 'logistics';
    default:
      return 'service_flex';
  }
}

function sizeForTile(
  districtKey: string | null | undefined,
  frontage: boolean,
  x: number,
  y: number,
): BusinessLotSize {
  if (frontage && (districtKey === 'exchange' || districtKey === 'harbor')) return 'large';
  if (frontage && (districtKey === 'midtown' || districtKey === 'commerce')) return 'medium';
  if (frontage) return 'small';
  return (x + y) % 3 === 0 ? 'small' : 'micro';
}

function districtValueBase(districtKey: string | null | undefined): number {
  switch (districtKey) {
    case 'heights':
      return 180;
    case 'midtown':
      return 300;
    case 'exchange':
      return 420;
    case 'makers':
      return 250;
    case 'commerce':
      return 340;
    case 'harbor':
      return 360;
    default:
      return 150;
  }
}

function districtTrafficBase(districtKey: string | null | undefined): number {
  switch (districtKey) {
    case 'heights':
      return 42;
    case 'midtown':
      return 68;
    case 'exchange':
      return 84;
    case 'makers':
      return 58;
    case 'commerce':
      return 73;
    case 'harbor':
      return 66;
    default:
      return 36;
  }
}

function districtDevelopmentBase(districtKey: string | null | undefined): number {
  switch (districtKey) {
    case 'heights':
      return 52;
    case 'midtown':
      return 70;
    case 'exchange':
      return 82;
    case 'makers':
      return 64;
    case 'commerce':
      return 76;
    case 'harbor':
      return 88;
    default:
      return 44;
  }
}

function createLandProfile(
  districtKey: string | null | undefined,
  frontage: boolean,
  x: number,
  y: number,
): SandboxLandProfile {
  const zoneType = zoneTypeForDistrict(districtKey);
  const size = sizeForTile(districtKey, frontage, x, y);
  const sizeMultiplier = size === 'large'
    ? 1.55
    : size === 'medium'
      ? 1.28
      : size === 'small'
        ? 1.08
        : 0.9;
  const frontageBonus = frontage ? 72 : 18;
  const adjacencyBonus = ((x + y) % 4) * 9;
  const valueXgp = Math.round((districtValueBase(districtKey) * sizeMultiplier) + frontageBonus + adjacencyBonus);
  const trafficScore = Math.min(
    100,
    Math.round(districtTrafficBase(districtKey) + (frontage ? 16 : 4) + ((x * 3 + y * 5) % 11)),
  );
  const developmentPotential = Math.min(
    100,
    Math.round(districtDevelopmentBase(districtKey) + (frontage ? 10 : 0) + ((x * 7 + y * 2) % 9)),
  );

  return {
    zoneType,
    size,
    valueXgp,
    trafficScore,
    developmentPotential,
  };
}

function labelForNodeType(nodeType: string): {
  kind: SandboxTileKind;
  shortLabel: string;
  description: string;
  actionTags: MapTileActionTag[];
} {
  const normalized = nodeType.toLowerCase();
  if (normalized === 'business') {
    return {
      kind: 'existing_business',
      shortLabel: 'BIZ',
      description: 'Main business lane for opening, operating, or restocking your active business.',
      actionTags: ['business_open', 'business_operate', 'business_inventory'],
    };
  }
  if (normalized === 'rideshare_hotspot') {
    return {
      kind: 'service_building',
      shortLabel: 'RSH',
      description: 'Mobility hotspot with stronger ride demand and faster routing.',
      actionTags: ['rideshare'],
    };
  }
  if (normalized === 'job_board') {
    return {
      kind: 'service_building',
      shortLabel: 'JOB',
      description: 'Career hub for reviewing available jobs, locked roles, certifications, and progression requirements.',
      actionTags: ['job_board'],
    };
  }
  if (normalized === 'work') {
    return {
      kind: 'service_building',
      shortLabel: 'WRK',
      description: 'Primary work destination and employment activity tile.',
      actionTags: ['work_shift'],
    };
  }
  if (normalized === 'grocery') {
    return {
      kind: 'service_building',
      shortLabel: 'GRY',
      description: 'Food and household essentials anchor. Use it for breakfast or lunch runs.',
      actionTags: ['meal_breakfast', 'meal_lunch'],
    };
  }
  if (normalized === 'bank') {
    return {
      kind: 'service_building',
      shortLabel: 'BNK',
      description: 'Deposits, withdrawals, and loan origination. Actions unlock in a later step.',
      actionTags: [],
    };
  }
  if (normalized === 'stock_center') {
    return {
      kind: 'service_building',
      shortLabel: 'STK',
      description: 'Stock market kiosk. Brokerage lane unlocks in a later step.',
      actionTags: [],
    };
  }
  if (normalized === 'certification_school') {
    return {
      kind: 'service_building',
      shortLabel: 'CRT',
      description: 'Training and licensing hub for job certifications.',
      actionTags: [],
    };
  }
  if (normalized === 'housing') {
    return {
      kind: 'service_building',
      shortLabel: 'HSG',
      description: 'Housing market entry point. Rent and purchase flows unlock in a later step.',
      actionTags: [],
    };
  }
  if (normalized === 'clinic') {
    return {
      kind: 'service_building',
      shortLabel: 'CLN',
      description: 'Health services and recovery treatment. Actions unlock in a later step.',
      actionTags: [],
    };
  }
  if (normalized === 'gas_station') {
    return {
      kind: 'service_building',
      shortLabel: 'GAS',
      description: 'Vehicle fueling and quick-spend anchor. Actions unlock in a later step.',
      actionTags: [],
    };
  }
  if (normalized === 'car_sale') {
    return {
      kind: 'service_building',
      shortLabel: 'CAR',
      description: 'Vehicle dealership. Purchase and upgrade lanes unlock in a later step.',
      actionTags: [],
    };
  }
  return {
    kind: 'service_building',
    shortLabel: 'BASE',
    description: 'Player-linked service tile in the active city network.',
    actionTags: [],
  };
}

function resolveNodeAnchors(nodes: MapNode[]): Record<string, { x: number; y: number }> {
  const anchors: Record<string, { x: number; y: number }> = { ...FIXED_NODE_ANCHORS };
  let dynamicIndex = 0;

  nodes.forEach((node) => {
    if (anchors[node.key]) return;
    const fallback = FLEX_NODE_ANCHORS[dynamicIndex];
    if (!fallback) return;
    anchors[node.key] = fallback;
    dynamicIndex += 1;
  });

  return anchors;
}

function createSpecialTileMap(
  nodes: MapNode[],
  travelOptions: TravelOptionSnapshot[],
  currentLocationKey: string,
): Record<string, TileSeed> {
  const tiles: Record<string, TileSeed> = {};

  STATIC_SPECIAL_TILES.forEach((tile) => {
    tiles[coordinateKey(tile.x, tile.y)] = tile;
  });

  const anchors = resolveNodeAnchors(nodes);
  const travelByDestination = Object.fromEntries(
    travelOptions.map((option) => [String(option.destination_key), option]),
  ) as Record<string, TravelOptionSnapshot>;

  nodes.forEach((node) => {
    const anchor = anchors[node.key];
    if (!anchor) return;
    const nodeMeta = labelForNodeType(node.node_type);
    const district = findDistrict(anchor.x, anchor.y);
    const travelOption = travelByDestination[node.key];
    tiles[coordinateKey(anchor.x, anchor.y)] = {
      x: anchor.x,
      y: anchor.y,
      kind: nodeMeta.kind,
      label: node.label,
      shortLabel: nodeMeta.shortLabel,
      description: travelOption
        ? `${nodeMeta.description} Travel cost: ${travelOption.time_cost_units} time unit${travelOption.time_cost_units === 1 ? '' : 's'}.`
        : nodeMeta.description,
      buildable: false,
      districtKey: district?.key || null,
      districtLabel: district?.label || null,
      nodeKey: node.key,
      nodeType: node.node_type,
      opportunityTier: node.opportunity_tier,
      actionTags: nodeMeta.actionTags,
    };
  });

  if (currentLocationKey && anchors[currentLocationKey]) {
    const current = anchors[currentLocationKey];
    const key = coordinateKey(current.x, current.y);
    const existing = tiles[key];
    if (existing) {
      tiles[key] = {
        ...existing,
        shortLabel: existing.shortLabel || 'YOU',
      };
    }
  }

  return tiles;
}

export function buildSandboxCityMap(options: {
  nodes: MapNode[];
  travelOptions?: TravelOptionSnapshot[];
  currentLocationKey: string;
}): SandboxCityMap {
  const nodes = options.nodes || [];
  const travelOptions = options.travelOptions || [];
  const currentLocationKey = String(options.currentLocationKey || '');
  const specialTileMap = createSpecialTileMap(nodes, travelOptions, currentLocationKey);
  const travelByDestination = Object.fromEntries(
    travelOptions.map((option) => [String(option.destination_key), option]),
  ) as Record<string, TravelOptionSnapshot>;

  const tiles: SandboxMapTile[] = [];
  const tileByKey: Record<string, SandboxMapTile> = {};
  const tileByCoordinate: Record<string, SandboxMapTile> = {};
  const tileByNodeKey: Record<string, SandboxMapTile> = {};

  for (let y = 0; y < MAP_ROWS; y += 1) {
    for (let x = 0; x < MAP_COLUMNS; x += 1) {
      const district = findDistrict(x, y);
      const special = specialTileMap[coordinateKey(x, y)];
      let tile: SandboxMapTile;

      if (isRoadTile(x, y)) {
        tile = {
          key: tileKey(x, y),
          x,
          y,
          kind: 'road',
          label: roadAxisForTile(x, y) === 'intersection' ? 'Junction' : 'Road',
          description: 'Street network for movement, routing, and frontage access.',
          districtKey: null,
          districtLabel: null,
          buildable: false,
          selectable: true,
          nodeKey: null,
          nodeType: null,
          opportunityTier: null,
          isCurrentLocation: false,
          roadAxis: roadAxisForTile(x, y),
          travelOption: null,
          actionTags: [],
          landProfile: null,
        };
      } else if (special) {
        tile = {
          key: tileKey(x, y),
          x,
          y,
          kind: special.kind,
          label: special.label,
          shortLabel: special.shortLabel,
          description: special.description,
          districtKey: special.districtKey ?? district?.key ?? null,
          districtLabel: special.districtLabel ?? district?.label ?? null,
          buildable: special.buildable ?? special.kind === 'building_slot',
          selectable: true,
          nodeKey: special.nodeKey ?? null,
          nodeType: special.nodeType ?? null,
          opportunityTier: special.opportunityTier ?? null,
          isCurrentLocation: special.nodeKey === currentLocationKey,
          roadAxis: null,
          travelOption: special.nodeKey ? travelByDestination[special.nodeKey] ?? null : null,
          actionTags: special.actionTags || [],
          landProfile: null,
        };
      } else if (district) {
        const frontage = isFrontageTile(x, y);
        const landProfile = createLandProfile(district.key, frontage, x, y);
        tile = {
          key: tileKey(x, y),
          x,
          y,
          kind: frontage ? 'building_slot' : 'empty_lot',
          label: frontage ? 'Buildable Frontage' : 'Open Lot',
          shortLabel: frontage ? 'LOT' : undefined,
          description: frontage
            ? `${district.label} frontage lot with ${landProfile.trafficScore}/100 traffic and ${landProfile.developmentPotential}/100 development upside.`
            : `${district.label} infill lot with ${landProfile.valueXgp} XGP land value and ${landProfile.zoneType.replace(/_/g, ' ')} zoning.`,
          districtKey: district.key,
          districtLabel: district.label,
          buildable: true,
          selectable: true,
          nodeKey: null,
          nodeType: null,
          opportunityTier: null,
          isCurrentLocation: false,
          roadAxis: null,
          travelOption: null,
          actionTags: [],
          landProfile,
        };
      } else {
        tile = {
          key: tileKey(x, y),
          x,
          y,
          kind: 'expansion_node',
          label: 'Expansion Buffer',
          shortLabel: 'EXP',
          description: 'Reserved outer-map tile for future district expansion.',
          districtKey: null,
          districtLabel: null,
          buildable: false,
          selectable: true,
          nodeKey: null,
          nodeType: null,
          opportunityTier: null,
          isCurrentLocation: false,
          roadAxis: null,
          travelOption: null,
          actionTags: [],
          landProfile: null,
        };
      }

      tiles.push(tile);
      tileByKey[tile.key] = tile;
      tileByCoordinate[coordinateKey(x, y)] = tile;
      if (tile.nodeKey) {
        tileByNodeKey[tile.nodeKey] = tile;
      }
    }
  }

  const currentLocationTileKey = tileByNodeKey[currentLocationKey]?.key || null;

  return {
    columns: MAP_COLUMNS,
    rows: MAP_ROWS,
    tileSize: MAP_TILE_SIZE,
    worldWidth: MAP_COLUMNS * MAP_TILE_SIZE,
    worldHeight: MAP_ROWS * MAP_TILE_SIZE,
    districts: DISTRICTS,
    tiles,
    tileByKey,
    tileByCoordinate,
    tileByNodeKey,
    currentLocationTileKey,
  };
}

export function describeTileKind(kind: SandboxTileKind): string {
  switch (kind) {
    case 'road':
      return 'Road';
    case 'building_slot':
      return 'Building Slot';
    case 'existing_business':
      return 'Existing Business';
    case 'service_building':
      return 'Service Building';
    case 'expansion_node':
      return 'Expansion Node';
    default:
      return 'Empty Lot';
  }
}

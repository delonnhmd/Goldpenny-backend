import type { TravelOptionSnapshot } from '@/types/gameplay';
import type { BusinessLandZoneType, BusinessLotSize } from '@/types/business';
import { alpha, theme } from '@/design/theme';

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
export type MapZoneTone = 'rural' | 'downtown';

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
  tone: MapZoneTone;
}

export interface SandboxZoneWash {
  key: MapZoneTone;
  label: 'RURAL' | 'DOWNTOWN';
  tone: MapZoneTone;
  x: number;
  y: number;
  width: number;
  height: number;
  fill: string;
  labelX: number;
  labelY: number;
  labelColor: string;
}

export interface SandboxRoadSegment {
  key: string;
  x: number;
  y: number;
  width: number;
  height: number;
  major: boolean;
}

export interface SandboxRiverGeometry {
  path: string;
  baseColor: string;
  highlightColor: string;
  strokeWidth: number;
  highlightWidth: number;
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
  zoneTone?: MapZoneTone | null;
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
  waterfront: boolean;
  visualScaleX: number;
  visualScaleY: number;
}

export interface SandboxCityMap {
  columns: number;
  rows: number;
  tileSize: number;
  worldWidth: number;
  worldHeight: number;
  districts: SandboxDistrict[];
  zones: SandboxZoneWash[];
  roads: SandboxRoadSegment[];
  river: SandboxRiverGeometry;
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

interface RoadSeed {
  key: string;
  x: number;
  y: number;
  width: number;
  height: number;
  major: boolean;
}

interface Point {
  x: number;
  y: number;
}

interface RiverSegment {
  start: Point;
  c1: Point;
  c2: Point;
  end: Point;
}

export const MAP_COLUMNS = 72;
export const MAP_ROWS = 46;
export const MAP_TILE_SIZE = 16;

const RIVER_WATERFRONT_DISTANCE_PX = MAP_TILE_SIZE * 1.42;

const DISTRICTS: SandboxDistrict[] = [
  {
    key: 'heights',
    label: 'Heights',
    subtitle: 'Rural homes + local services',
    tone: 'rural',
  },
  {
    key: 'makers',
    label: 'Makers Row',
    subtitle: 'Light production + flexible lots',
    tone: 'rural',
  },
  {
    key: 'exchange',
    label: 'Exchange',
    subtitle: 'River-adjacent trading lots',
    tone: 'rural',
  },
  {
    key: 'midtown',
    label: 'Midtown',
    subtitle: 'Dense service economy core',
    tone: 'downtown',
  },
  {
    key: 'commerce',
    label: 'Commerce',
    subtitle: 'High-opportunity business belt',
    tone: 'downtown',
  },
  {
    key: 'harbor',
    label: 'Harbor',
    subtitle: 'Late-game heavy expansion',
    tone: 'downtown',
  },
];

const DISTRICT_BY_KEY = Object.fromEntries(
  DISTRICTS.map((district) => [district.key, district]),
) as Record<string, SandboxDistrict>;

const ROAD_SEEDS: RoadSeed[] = [
  { key: 'h_1_w', x: 0, y: 6, width: 30, height: 1, major: true },
  { key: 'h_1_e', x: 36, y: 6, width: 36, height: 1, major: true },
  { key: 'h_2_w', x: 2, y: 12, width: 24, height: 1, major: false },
  { key: 'h_2_e', x: 30, y: 12, width: 42, height: 1, major: true },
  { key: 'h_3_w', x: 6, y: 19, width: 22, height: 1, major: false },
  { key: 'h_3_e', x: 32, y: 19, width: 40, height: 2, major: true },
  { key: 'h_4_w', x: 0, y: 27, width: 22, height: 1, major: false },
  { key: 'h_4_e', x: 28, y: 27, width: 44, height: 1, major: true },
  { key: 'h_5_w', x: 4, y: 35, width: 20, height: 1, major: false },
  { key: 'h_5_e', x: 30, y: 35, width: 42, height: 1, major: true },
  { key: 'h_6_w', x: 8, y: 41, width: 18, height: 1, major: false },
  { key: 'h_6_e', x: 36, y: 41, width: 36, height: 1, major: true },
  { key: 'v_1_n', x: 8, y: 0, width: 1, height: 18, major: false },
  { key: 'v_1_s', x: 8, y: 22, width: 1, height: 24, major: false },
  { key: 'v_2_n', x: 16, y: 4, width: 1, height: 16, major: false },
  { key: 'v_2_s', x: 16, y: 24, width: 1, height: 22, major: false },
  { key: 'v_3_n', x: 26, y: 0, width: 2, height: 15, major: true },
  { key: 'v_3_s', x: 26, y: 19, width: 2, height: 27, major: true },
  { key: 'v_4_n', x: 36, y: 2, width: 1, height: 18, major: false },
  { key: 'v_4_s', x: 36, y: 22, width: 1, height: 22, major: false },
  { key: 'v_5_n', x: 46, y: 0, width: 2, height: 20, major: true },
  { key: 'v_5_s', x: 46, y: 24, width: 2, height: 22, major: true },
  { key: 'v_6_n', x: 56, y: 4, width: 1, height: 18, major: false },
  { key: 'v_6_s', x: 56, y: 22, width: 1, height: 24, major: false },
  { key: 'v_7_n', x: 64, y: 0, width: 2, height: 18, major: true },
  { key: 'v_7_s', x: 64, y: 20, width: 2, height: 26, major: true },
  { key: 'v_8', x: 69, y: 8, width: 1, height: 38, major: false },
];

const RIVER_SEGMENTS: RiverSegment[] = [
  {
    start: { x: -4, y: 15 },
    c1: { x: 8, y: 6 },
    c2: { x: 20, y: 10 },
    end: { x: 30, y: 18 },
  },
  {
    start: { x: 30, y: 18 },
    c1: { x: 42, y: 28 },
    c2: { x: 52, y: 11 },
    end: { x: 63, y: 20 },
  },
  {
    start: { x: 63, y: 20 },
    c1: { x: 72, y: 30 },
    c2: { x: 82, y: 16 },
    end: { x: 88, y: 25 },
  },
];

const STATIC_SPECIAL_TILES: TileSeed[] = [
  {
    x: 60,
    y: 31,
    kind: 'service_building',
    label: 'Food Truck Court',
    shortLabel: 'DIN',
    description: 'Dinner hotspot for restaurant and food truck spending.',
    actionTags: ['meal_dinner'],
  },
  {
    x: 22,
    y: 28,
    kind: 'service_building',
    label: 'Pocket Park',
    shortLabel: 'REST',
    description: 'Leisure pocket for timed recovery and low-pressure downtime.',
    actionTags: ['recovery'],
  },
  {
    x: 68,
    y: 6,
    kind: 'expansion_node',
    label: 'North Expansion',
    shortLabel: 'EXP',
    description: 'Future district unlock node for larger projects.',
  },
  {
    x: 4,
    y: 40,
    kind: 'expansion_node',
    label: 'West Expansion',
    shortLabel: 'EXP',
    description: 'Reserved edge tile for future neighborhood growth.',
  },
  {
    x: 69,
    y: 43,
    kind: 'expansion_node',
    label: 'South Expansion',
    shortLabel: 'EXP',
    description: 'Future harbor-side buildout anchor.',
  },
];

const FIXED_NODE_ANCHORS: Record<string, { x: number; y: number }> = {
  home: { x: 12, y: 34 },
  grocery: { x: 11, y: 8 },
  rideshare_hotspot_suburban: { x: 18, y: 29 },
  job_center: { x: 47, y: 10 },
  work: { x: 52, y: 25 },
  rideshare_hotspot_downtown: { x: 44, y: 16 },
  business_spot: { x: 60, y: 30 },
  bank: { x: 56, y: 10 },
  stock_center: { x: 65, y: 13 },
  certification_school: { x: 50, y: 15 },
  housing: { x: 18, y: 32 },
  clinic: { x: 25, y: 33 },
  gas_station: { x: 9, y: 39 },
  car_sale: { x: 68, y: 18 },
};

const FLEX_NODE_ANCHORS = [
  { x: 30, y: 10 },
  { x: 38, y: 24 },
  { x: 21, y: 12 },
  { x: 28, y: 31 },
  { x: 56, y: 19 },
  { x: 66, y: 26 },
];

const ROAD_TILE_SET = buildRoadTileSet();
const RIVER_SAMPLE_POINTS = sampleRiverPoints(MAP_TILE_SIZE);

function coordinateKey(x: number, y: number): string {
  return `${x}:${y}`;
}

function tileKey(x: number, y: number): string {
  return `tile_${x}_${y}`;
}

function zoneToneForTile(x: number, y: number): MapZoneTone {
  const diagonalSplit = (x * 0.32) + 9;
  return y > diagonalSplit ? 'downtown' : 'rural';
}

function districtKeyForTile(x: number, y: number, tone: MapZoneTone): string {
  if (tone === 'rural') {
    if (y < 13) return 'heights';
    if (x > 24 && y < 28) return 'exchange';
    return 'makers';
  }
  if (y < 17) return 'midtown';
  if (x > 56 || y > 36) return 'harbor';
  return 'commerce';
}

function findDistrict(x: number, y: number): SandboxDistrict | undefined {
  const tone = zoneToneForTile(x, y);
  return DISTRICT_BY_KEY[districtKeyForTile(x, y, tone)];
}

function buildRoadTileSet(): Set<string> {
  const set = new Set<string>();
  ROAD_SEEDS.forEach((seed) => {
    for (let y = seed.y; y < seed.y + seed.height; y += 1) {
      for (let x = seed.x; x < seed.x + seed.width; x += 1) {
        if (x < 0 || y < 0 || x >= MAP_COLUMNS || y >= MAP_ROWS) continue;
        set.add(coordinateKey(x, y));
      }
    }
  });
  return set;
}

function isRoadTile(x: number, y: number): boolean {
  return ROAD_TILE_SET.has(coordinateKey(x, y));
}

function roadAxisForTile(x: number, y: number): RoadAxis {
  if (!isRoadTile(x, y)) return null;
  const horizontal = isRoadTile(x - 1, y) || isRoadTile(x + 1, y);
  const vertical = isRoadTile(x, y - 1) || isRoadTile(x, y + 1);
  if (horizontal && vertical) return 'intersection';
  if (horizontal) return 'horizontal';
  if (vertical) return 'vertical';
  return 'horizontal';
}

function hasRoadFrontage(x: number, y: number): boolean {
  return (
    isRoadTile(x - 1, y)
    || isRoadTile(x + 1, y)
    || isRoadTile(x, y - 1)
    || isRoadTile(x, y + 1)
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
  district: SandboxDistrict | undefined,
  frontage: boolean,
  x: number,
  y: number,
): BusinessLotSize {
  const seed = (x * 37 + y * 17) % 10;
  if (district?.tone === 'rural') {
    if (frontage && seed >= 7) return 'large';
    if (frontage) return 'medium';
    return seed % 2 === 0 ? 'medium' : 'small';
  }
  if (frontage && seed >= 6) return 'medium';
  if (frontage) return 'small';
  return seed % 3 === 0 ? 'small' : 'micro';
}

function visualScaleForTile(tone: MapZoneTone, x: number, y: number): { scaleX: number; scaleY: number } {
  const seed = (x * 19 + y * 13) % 9;
  if (tone === 'rural') {
    return {
      scaleX: 0.9 + ((seed % 4) * 0.04),
      scaleY: 0.88 + (((seed + 2) % 3) * 0.05),
    };
  }
  return {
    scaleX: 0.7 + ((seed % 3) * 0.07),
    scaleY: 0.7 + (((seed + 1) % 3) * 0.07),
  };
}

function districtValueBase(districtKey: string | null | undefined): number {
  switch (districtKey) {
    case 'heights':
      return 170;
    case 'makers':
      return 210;
    case 'exchange':
      return 280;
    case 'midtown':
      return 320;
    case 'commerce':
      return 360;
    case 'harbor':
      return 410;
    default:
      return 160;
  }
}

function districtTrafficBase(districtKey: string | null | undefined): number {
  switch (districtKey) {
    case 'heights':
      return 38;
    case 'makers':
      return 50;
    case 'exchange':
      return 64;
    case 'midtown':
      return 72;
    case 'commerce':
      return 79;
    case 'harbor':
      return 74;
    default:
      return 34;
  }
}

function districtDevelopmentBase(districtKey: string | null | undefined): number {
  switch (districtKey) {
    case 'heights':
      return 48;
    case 'makers':
      return 57;
    case 'exchange':
      return 67;
    case 'midtown':
      return 73;
    case 'commerce':
      return 81;
    case 'harbor':
      return 86;
    default:
      return 44;
  }
}

function createLandProfile(
  district: SandboxDistrict | undefined,
  frontage: boolean,
  x: number,
  y: number,
): SandboxLandProfile {
  const districtKey = district?.key;
  const zoneType = zoneTypeForDistrict(districtKey);
  const size = sizeForTile(district, frontage, x, y);
  const sizeMultiplier = size === 'large'
    ? 1.56
    : size === 'medium'
      ? 1.29
      : size === 'small'
        ? 1.06
        : 0.9;
  const frontageBonus = frontage ? 68 : 16;
  const adjacencyBonus = ((x + y) % 5) * 8;
  const valueXgp = Math.round((districtValueBase(districtKey) * sizeMultiplier) + frontageBonus + adjacencyBonus);
  const trafficScore = Math.min(
    100,
    Math.round(districtTrafficBase(districtKey) + (frontage ? 14 : 3) + ((x * 3 + y * 5) % 12)),
  );
  const developmentPotential = Math.min(
    100,
    Math.round(districtDevelopmentBase(districtKey) + (frontage ? 9 : 1) + ((x * 7 + y * 2) % 9)),
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
      description: 'Career hub for reviewing available jobs, locked roles, and progression requirements.',
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

function cubicBezierPoint(segment: RiverSegment, t: number): Point {
  const inv = 1 - t;
  const invSq = inv * inv;
  const tSq = t * t;
  const x = (invSq * inv * segment.start.x)
    + (3 * invSq * t * segment.c1.x)
    + (3 * inv * tSq * segment.c2.x)
    + (tSq * t * segment.end.x);
  const y = (invSq * inv * segment.start.y)
    + (3 * invSq * t * segment.c1.y)
    + (3 * inv * tSq * segment.c2.y)
    + (tSq * t * segment.end.y);
  return { x, y };
}

function sampleRiverPoints(tileSize: number): Point[] {
  const samples: Point[] = [];
  RIVER_SEGMENTS.forEach((segment, segmentIndex) => {
    const steps = 28;
    const startStep = segmentIndex === 0 ? 0 : 1;
    for (let step = startStep; step <= steps; step += 1) {
      const point = cubicBezierPoint(segment, step / steps);
      samples.push({
        x: point.x * tileSize,
        y: point.y * tileSize,
      });
    }
  });
  return samples;
}

function isWaterfrontTile(x: number, y: number): boolean {
  const centerX = (x * MAP_TILE_SIZE) + (MAP_TILE_SIZE / 2);
  const centerY = (y * MAP_TILE_SIZE) + (MAP_TILE_SIZE / 2);
  const thresholdSq = RIVER_WATERFRONT_DISTANCE_PX * RIVER_WATERFRONT_DISTANCE_PX;

  for (let index = 0; index < RIVER_SAMPLE_POINTS.length; index += 1) {
    const point = RIVER_SAMPLE_POINTS[index];
    const dx = point.x - centerX;
    const dy = point.y - centerY;
    const distanceSq = (dx * dx) + (dy * dy);
    if (distanceSq <= thresholdSq) return true;
  }

  return false;
}

function buildZoneWashes(tileSize: number): SandboxZoneWash[] {
  const worldWidth = MAP_COLUMNS * tileSize;
  const worldHeight = MAP_ROWS * tileSize;

  return [
    {
      key: 'rural',
      label: 'RURAL',
      tone: 'rural',
      x: 0,
      y: 0,
      width: Math.round(worldWidth * 0.56),
      height: Math.round(worldHeight * 0.54),
      fill: alpha(theme.ui.positive, 0.14),
      labelX: Math.round(tileSize * 5),
      labelY: Math.round(tileSize * 8),
      labelColor: theme.ui.positive,
    },
    {
      key: 'downtown',
      label: 'DOWNTOWN',
      tone: 'downtown',
      x: Math.round(worldWidth * 0.28),
      y: Math.round(worldHeight * 0.22),
      width: Math.round(worldWidth * 0.72),
      height: Math.round(worldHeight * 0.78),
      fill: alpha(theme.ui.action, 0.12),
      labelX: Math.round(worldWidth * 0.68),
      labelY: Math.round(worldHeight * 0.72),
      labelColor: theme.ui.info,
    },
  ];
}

function buildRoadSegments(tileSize: number): SandboxRoadSegment[] {
  return ROAD_SEEDS.map((seed) => ({
    key: seed.key,
    x: seed.x * tileSize,
    y: seed.y * tileSize,
    width: seed.width * tileSize,
    height: seed.height * tileSize,
    major: seed.major,
  }));
}

function buildRiverGeometry(tileSize: number): SandboxRiverGeometry {
  const first = RIVER_SEGMENTS[0];
  let path = `M ${first.start.x * tileSize} ${first.start.y * tileSize}`;
  RIVER_SEGMENTS.forEach((segment) => {
    path += ` C ${segment.c1.x * tileSize} ${segment.c1.y * tileSize}, ${segment.c2.x * tileSize} ${segment.c2.y * tileSize}, ${segment.end.x * tileSize} ${segment.end.y * tileSize}`;
  });

  return {
    path,
    baseColor: alpha(theme.ui.info, 0.44),
    highlightColor: alpha(theme.ui.info, 0.74),
    strokeWidth: tileSize * 1.72,
    highlightWidth: tileSize * 0.46,
  };
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
      const coordinate = coordinateKey(x, y);
      const special = specialTileMap[coordinate];
      const zoneTone = zoneToneForTile(x, y);
      const district = findDistrict(x, y);
      const waterfront = !isRoadTile(x, y) && isWaterfrontTile(x, y);
      const visualScale = visualScaleForTile(zoneTone, x, y);

      let tile: SandboxMapTile;

      if (special) {
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
          zoneTone,
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
          waterfront,
          visualScaleX: special.kind === 'service_building' || special.kind === 'existing_business'
            ? 0.92
            : visualScale.scaleX,
          visualScaleY: special.kind === 'service_building' || special.kind === 'existing_business'
            ? 0.92
            : visualScale.scaleY,
        };
      } else if (isRoadTile(x, y)) {
        tile = {
          key: tileKey(x, y),
          x,
          y,
          kind: 'road',
          label: roadAxisForTile(x, y) === 'intersection' ? 'Junction' : 'Road',
          description: 'Dark asphalt movement lane connecting district blocks.',
          districtKey: null,
          districtLabel: null,
          zoneTone,
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
          waterfront: false,
          visualScaleX: 1,
          visualScaleY: 1,
        };
      } else {
        const frontage = hasRoadFrontage(x, y);
        const landProfile = createLandProfile(district, frontage, x, y);
        const districtLabel = district?.label || (zoneTone === 'rural' ? 'Rural Edge' : 'Downtown Edge');
        const districtKey = district?.key || null;
        const waterfrontNote = waterfront
          ? ' Waterfront adjacency flagged for future value bonus hooks.'
          : '';
        tile = {
          key: tileKey(x, y),
          x,
          y,
          kind: frontage ? 'building_slot' : 'empty_lot',
          label: frontage ? 'Buildable Frontage' : 'Open Lot',
          shortLabel: frontage ? 'LOT' : undefined,
          description: frontage
            ? `${districtLabel} frontage lot with ${landProfile.trafficScore}/100 traffic and ${landProfile.developmentPotential}/100 development upside.${waterfrontNote}`
            : `${districtLabel} infill lot with ${landProfile.valueXgp} XGP land value and ${landProfile.zoneType.replace(/_/g, ' ')} zoning.${waterfrontNote}`,
          districtKey,
          districtLabel,
          zoneTone,
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
          waterfront,
          visualScaleX: visualScale.scaleX,
          visualScaleY: visualScale.scaleY,
        };
      }

      tiles.push(tile);
      tileByKey[tile.key] = tile;
      tileByCoordinate[coordinate] = tile;
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
    zones: buildZoneWashes(MAP_TILE_SIZE),
    roads: buildRoadSegments(MAP_TILE_SIZE),
    river: buildRiverGeometry(MAP_TILE_SIZE),
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

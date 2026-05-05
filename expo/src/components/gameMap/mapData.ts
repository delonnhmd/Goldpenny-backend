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

export type SandboxZoneKey = 'rural' | 'downtown' | 'outer';

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
  tone: SandboxZoneKey;
  x: number;
  y: number;
  width: number;
  height: number;
  fill: string;
  accent: string;
  labelColor: string;
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
  zoneTone: SandboxZoneKey | 'river';
  buildable: boolean;
  selectable: boolean;
  waterfront: boolean;
  nodeKey?: string | null;
  nodeType?: string | null;
  opportunityTier?: string | null;
  isCurrentLocation: boolean;
  roadAxis: RoadAxis;
  travelOption?: TravelOptionSnapshot | null;
  actionTags: MapTileActionTag[];
  landProfile?: SandboxLandProfile | null;
}

export interface RiverGeometry {
  controlPoints: Array<{ x: number; y: number }>;
  bandPx: number;
  centerlineSamples: Array<{ x: number; y: number }>;
}

export interface SandboxCityMap {
  columns: number;
  rows: number;
  tileSize: number;
  worldWidth: number;
  worldHeight: number;
  districts: SandboxDistrict[];
  river: RiverGeometry;
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

// Step 97F — denser grid with smaller tiles for sharper zoom range and a
// real city silhouette instead of a chess board.
export const MAP_COLUMNS = 60;
export const MAP_ROWS = 44;
export const MAP_TILE_SIZE = 16;
const WORLD_W = MAP_COLUMNS * MAP_TILE_SIZE;
const WORLD_H = MAP_ROWS * MAP_TILE_SIZE;

// Two-zone layout. Rural sits in the upper-left, downtown in the lower-right.
// The river cuts diagonally between them.
const RURAL_BOUNDS = { x: 0, y: 0, width: 30, height: 24 };
const DOWNTOWN_BOUNDS = { x: 28, y: 20, width: 32, height: 24 };

const DISTRICTS: SandboxDistrict[] = [
  {
    key: 'rural',
    label: 'RURAL',
    subtitle: 'Sparse roads · larger blocks',
    tone: 'rural',
    x: RURAL_BOUNDS.x,
    y: RURAL_BOUNDS.y,
    width: RURAL_BOUNDS.width,
    height: RURAL_BOUNDS.height,
    fill: alpha(theme.gameUi.success, 0.1),
    accent: theme.gameUi.success,
    labelColor: theme.gameUi.success,
  },
  {
    key: 'downtown',
    label: 'DOWNTOWN',
    subtitle: 'Dense grid · faster traffic',
    tone: 'downtown',
    x: DOWNTOWN_BOUNDS.x,
    y: DOWNTOWN_BOUNDS.y,
    width: DOWNTOWN_BOUNDS.width,
    height: DOWNTOWN_BOUNDS.height,
    fill: alpha(theme.gameUi.primary, 0.12),
    accent: theme.gameUi.primary,
    labelColor: theme.gameUi.icons.openSlot,
  },
];

// River centerline (column,row) anchors. Smooth bezier evaluated by
// piecewise quadratic interpolation at render time.
const RIVER_ANCHORS: Array<{ col: number; row: number }> = [
  { col: 60, row: 9 },
  { col: 48, row: 14 },
  { col: 36, row: 21 },
  { col: 24, row: 26 },
  { col: 12, row: 30 },
  { col: 0, row: 35 },
];

const RIVER_BAND_PX = MAP_TILE_SIZE * 1.6;

function riverRowAtColumn(col: number): number {
  // Linear interpolation between adjacent anchors gives a smooth-enough
  // centerline for tile-zone classification. The visual river uses a true
  // bezier path drawn by GameMap.
  const last = RIVER_ANCHORS[0];
  const first = RIVER_ANCHORS[RIVER_ANCHORS.length - 1];
  if (col >= last.col) return last.row;
  if (col <= first.col) return first.row;
  for (let i = RIVER_ANCHORS.length - 1; i > 0; i -= 1) {
    const a = RIVER_ANCHORS[i];
    const b = RIVER_ANCHORS[i - 1];
    const lo = Math.min(a.col, b.col);
    const hi = Math.max(a.col, b.col);
    if (col >= lo && col <= hi) {
      const t = (col - a.col) / (b.col - a.col);
      return a.row + ((b.row - a.row) * t);
    }
  }
  return last.row;
}

function riverCenterlineSamples(): Array<{ x: number; y: number }> {
  const samples: Array<{ x: number; y: number }> = [];
  const step = 4;
  for (let col = 0; col <= MAP_COLUMNS; col += step) {
    samples.push({
      x: col * MAP_TILE_SIZE,
      y: riverRowAtColumn(col) * MAP_TILE_SIZE,
    });
  }
  return samples;
}

function distanceFromRiverRows(x: number, y: number): number {
  return Math.abs(y - riverRowAtColumn(x + 0.5));
}

function inRiverBand(x: number, y: number): boolean {
  // Treat the band as ~1.4 tile rows wide so the SVG ribbon visually covers
  // the masked cells without leaving a hard chessboard edge.
  return distanceFromRiverRows(x, y) <= 0.7;
}

function isWaterfrontAdjacency(x: number, y: number): boolean {
  if (inRiverBand(x, y)) return false;
  return distanceFromRiverRows(x, y) <= 1.6;
}

function inRural(x: number, y: number): boolean {
  return (
    x >= RURAL_BOUNDS.x
    && x < RURAL_BOUNDS.x + RURAL_BOUNDS.width
    && y >= RURAL_BOUNDS.y
    && y < RURAL_BOUNDS.y + RURAL_BOUNDS.height
  );
}

function inDowntown(x: number, y: number): boolean {
  return (
    x >= DOWNTOWN_BOUNDS.x
    && x < DOWNTOWN_BOUNDS.x + DOWNTOWN_BOUNDS.width
    && y >= DOWNTOWN_BOUNDS.y
    && y < DOWNTOWN_BOUNDS.y + DOWNTOWN_BOUNDS.height
  );
}

function zoneOf(x: number, y: number): SandboxZoneKey | 'river' {
  if (inRiverBand(x, y)) return 'river';
  // River is the boundary; pick the zone that contains the cell, falling
  // back to the side of the river for outer cells.
  if (inDowntown(x, y) && !inRural(x, y)) return 'downtown';
  if (inRural(x, y) && !inDowntown(x, y)) return 'rural';
  if (inRural(x, y) && inDowntown(x, y)) {
    // Overlap region — split by river side.
    return y < riverRowAtColumn(x + 0.5) ? 'rural' : 'downtown';
  }
  // Outer fringe: classify by river side so the styling stays coherent.
  return y < riverRowAtColumn(x + 0.5) ? 'rural' : 'downtown';
}

// Length-varied road bands. Each entry is a half-open span [start, end) on
// the cross-axis — the irregular endpoints break the chessboard look and
// give the grid believable block sizes.
const RURAL_HORIZONTAL_ROADS: Array<{ row: number; from: number; to: number }> = [
  { row: 5, from: 0, to: 22 },
  { row: 12, from: 4, to: 28 },
  { row: 18, from: 0, to: 24 },
];
const RURAL_VERTICAL_ROADS: Array<{ col: number; from: number; to: number }> = [
  { col: 7, from: 0, to: 22 },
  { col: 16, from: 0, to: 18 },
  { col: 24, from: 4, to: 22 },
];

const DOWNTOWN_HORIZONTAL_ROADS: Array<{ row: number; from: number; to: number }> = [
  { row: 23, from: 30, to: 60 },
  { row: 27, from: 28, to: 56 },
  { row: 31, from: 30, to: 60 },
  { row: 35, from: 28, to: 58 },
  { row: 39, from: 32, to: 60 },
];
const DOWNTOWN_VERTICAL_ROADS: Array<{ col: number; from: number; to: number }> = [
  { col: 32, from: 22, to: 44 },
  { col: 37, from: 20, to: 42 },
  { col: 41, from: 22, to: 44 },
  { col: 46, from: 20, to: 44 },
  { col: 51, from: 22, to: 42 },
  { col: 56, from: 20, to: 44 },
];

function roadAxisAt(x: number, y: number): RoadAxis {
  let horizontal = false;
  let vertical = false;
  for (const band of RURAL_HORIZONTAL_ROADS) {
    if (y === band.row && x >= band.from && x < band.to) horizontal = true;
  }
  for (const band of DOWNTOWN_HORIZONTAL_ROADS) {
    if (y === band.row && x >= band.from && x < band.to) horizontal = true;
  }
  for (const band of RURAL_VERTICAL_ROADS) {
    if (x === band.col && y >= band.from && y < band.to) vertical = true;
  }
  for (const band of DOWNTOWN_VERTICAL_ROADS) {
    if (x === band.col && y >= band.from && y < band.to) vertical = true;
  }
  if (horizontal && vertical) return 'intersection';
  if (horizontal) return 'horizontal';
  if (vertical) return 'vertical';
  return null;
}

function isRoadTile(x: number, y: number): boolean {
  return roadAxisAt(x, y) !== null;
}

function isFrontageTile(x: number, y: number): boolean {
  const axis = roadAxisAt(x, y);
  if (axis !== null) return false;
  // A buildable frontage is any cell directly touching a road in any
  // cardinal direction. Gives downtown more frontage per row, rural fewer.
  return (
    isRoadTile(x + 1, y)
    || isRoadTile(x - 1, y)
    || isRoadTile(x, y + 1)
    || isRoadTile(x, y - 1)
  );
}

function zoneTypeForZone(zone: SandboxZoneKey | 'river'): BusinessLandZoneType {
  if (zone === 'downtown') return 'mixed_use';
  if (zone === 'rural') return 'residential_edge';
  return 'service_flex';
}

function sizeForTile(zone: SandboxZoneKey | 'river', frontage: boolean, x: number, y: number): BusinessLotSize {
  if (zone === 'downtown' && frontage) return ((x + y) % 4 === 0 ? 'medium' : 'small');
  if (zone === 'downtown') return ((x + y) % 5 === 0 ? 'small' : 'micro');
  // Rural — bigger varied lots.
  if (zone === 'rural' && frontage) return ((x * 2 + y) % 3 === 0 ? 'large' : 'medium');
  if (zone === 'rural') return ((x + y * 3) % 4 === 0 ? 'medium' : 'small');
  return 'micro';
}

function zoneValueBase(zone: SandboxZoneKey | 'river'): number {
  if (zone === 'downtown') return 360;
  if (zone === 'rural') return 200;
  return 160;
}

function zoneTrafficBase(zone: SandboxZoneKey | 'river'): number {
  if (zone === 'downtown') return 74;
  if (zone === 'rural') return 44;
  return 34;
}

function zoneDevelopmentBase(zone: SandboxZoneKey | 'river'): number {
  if (zone === 'downtown') return 78;
  if (zone === 'rural') return 56;
  return 40;
}

function createLandProfile(
  zone: SandboxZoneKey | 'river',
  frontage: boolean,
  waterfront: boolean,
  x: number,
  y: number,
): SandboxLandProfile {
  const zoneType = zoneTypeForZone(zone);
  const size = sizeForTile(zone, frontage, x, y);
  const sizeMultiplier = size === 'large'
    ? 1.55
    : size === 'medium'
      ? 1.28
      : size === 'small'
        ? 1.08
        : 0.9;
  const frontageBonus = frontage ? 64 : 14;
  const waterfrontBonus = waterfront ? 48 : 0;
  const adjacencyBonus = ((x + y) % 4) * 8;
  const valueXgp = Math.round(
    (zoneValueBase(zone) * sizeMultiplier) + frontageBonus + waterfrontBonus + adjacencyBonus,
  );
  const trafficScore = Math.min(
    100,
    Math.round(zoneTrafficBase(zone) + (frontage ? 14 : 4) + (waterfront ? 6 : 0) + ((x * 3 + y * 5) % 11)),
  );
  const developmentPotential = Math.min(
    100,
    Math.round(zoneDevelopmentBase(zone) + (frontage ? 10 : 0) + (waterfront ? 4 : 0) + ((x * 7 + y * 2) % 9)),
  );

  return {
    zoneType,
    size,
    valueXgp,
    trafficScore,
    developmentPotential,
  };
}

const STATIC_SPECIAL_TILES: TileSeed[] = [
  {
    x: 50,
    y: 26,
    kind: 'service_building',
    label: 'Food Truck Court',
    shortLabel: 'DIN',
    description: 'Dinner hotspot for restaurant and food truck spending.',
    actionTags: ['meal_dinner'],
  },
  {
    x: 17,
    y: 16,
    kind: 'service_building',
    label: 'Pocket Park',
    shortLabel: 'REST',
    description: 'Leisure pocket for timed recovery and low-pressure downtime.',
    actionTags: ['recovery'],
  },
  {
    x: 56,
    y: 22,
    kind: 'expansion_node',
    label: 'East Expansion',
    shortLabel: 'EXP',
    description: 'Inactive city boundary.',
  },
  {
    x: 3,
    y: 41,
    kind: 'expansion_node',
    label: 'South Expansion',
    shortLabel: 'EXP',
    description: 'Reserved waterfront boundary.',
  },
  {
    x: 56,
    y: 41,
    kind: 'expansion_node',
    label: 'Harbor Expansion',
    shortLabel: 'EXP',
    description: 'Reserved harbor boundary.',
  },
];

// Anchor coordinates remapped onto the 60x44 grid so each node still lands
// in its zone of intent.
const FIXED_NODE_ANCHORS: Record<string, { x: number; y: number }> = {
  home: { x: 8, y: 14 },
  grocery: { x: 12, y: 6 },
  rideshare_hotspot_suburban: { x: 22, y: 7 },
  job_center: { x: 40, y: 26 },
  work: { x: 45, y: 36 },
  rideshare_hotspot_downtown: { x: 48, y: 24 },
  business_spot: { x: 50, y: 32 },
  bank: { x: 38, y: 40 },
  certification_school: { x: 44, y: 30 },
  housing: { x: 5, y: 18 },
  clinic: { x: 16, y: 10 },
};

const FLEX_NODE_ANCHORS = [
  { x: 24, y: 9 },
  { x: 50, y: 38 },
  { x: 14, y: 17 },
  { x: 42, y: 24 },
  { x: 30, y: 36 },
];

function coordinateKey(x: number, y: number): string {
  return `${x}:${y}`;
}

function tileKey(x: number, y: number): string {
  return `tile_${x}_${y}`;
}

function findDistrictForZone(zone: SandboxZoneKey | 'river'): SandboxDistrict | undefined {
  if (zone === 'rural') return DISTRICTS[0];
  if (zone === 'downtown') return DISTRICTS[1];
  return undefined;
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
      description: 'Cash and credit landmark.',
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
      description: 'Housing landmark.',
      actionTags: [],
    };
  }
  if (normalized === 'clinic') {
    return {
      kind: 'service_building',
      shortLabel: 'CLN',
      description: 'Health and recovery landmark.',
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
    const zone = zoneOf(anchor.x, anchor.y);
    const district = findDistrictForZone(zone);
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
      const zone = zoneOf(x, y);
      const district = findDistrictForZone(zone);
      const waterfront = isWaterfrontAdjacency(x, y);
      const special = specialTileMap[coordinateKey(x, y)];
      let tile: SandboxMapTile;

      if (zone === 'river') {
        tile = {
          key: tileKey(x, y),
          x,
          y,
          kind: 'expansion_node',
          label: 'River',
          shortLabel: '',
          description: 'River corridor. Adjacent waterfront lots gain demand and value upside.',
          districtKey: null,
          districtLabel: null,
          zoneTone: 'river',
          buildable: false,
          selectable: false,
          waterfront: false,
          nodeKey: null,
          nodeType: null,
          opportunityTier: null,
          isCurrentLocation: false,
          roadAxis: null,
          travelOption: null,
          actionTags: [],
          landProfile: null,
        };
      } else if (isRoadTile(x, y)) {
        const axis = roadAxisAt(x, y);
        tile = {
          key: tileKey(x, y),
          x,
          y,
          kind: 'road',
          label: axis === 'intersection' ? 'Junction' : 'Road',
          description: 'Street network for movement, routing, and frontage access.',
          districtKey: district?.key || null,
          districtLabel: district?.label || null,
          zoneTone: zone,
          buildable: false,
          selectable: true,
          waterfront,
          nodeKey: null,
          nodeType: null,
          opportunityTier: null,
          isCurrentLocation: false,
          roadAxis: axis,
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
          zoneTone: zone,
          buildable: special.buildable ?? special.kind === 'building_slot',
          selectable: true,
          waterfront,
          nodeKey: special.nodeKey ?? null,
          nodeType: special.nodeType ?? null,
          opportunityTier: special.opportunityTier ?? null,
          isCurrentLocation: special.nodeKey === currentLocationKey,
          roadAxis: null,
          travelOption: special.nodeKey ? travelByDestination[special.nodeKey] ?? null : null,
          actionTags: special.actionTags || [],
          landProfile: null,
        };
      } else {
        const frontage = isFrontageTile(x, y);
        const landProfile = createLandProfile(zone, frontage, waterfront, x, y);
        tile = {
          key: tileKey(x, y),
          x,
          y,
          kind: frontage ? 'building_slot' : 'empty_lot',
          label: frontage ? 'Buildable Frontage' : 'Open Lot',
          shortLabel: frontage ? 'LOT' : undefined,
          description: frontage
            ? `${district?.label || 'Outer'} frontage lot with ${landProfile.trafficScore}/100 traffic and ${landProfile.developmentPotential}/100 development upside.`
            : `${district?.label || 'Outer'} infill lot with ${landProfile.valueXgp} XGP land value and ${landProfile.zoneType.replace(/_/g, ' ')} zoning.`,
          districtKey: district?.key || null,
          districtLabel: district?.label || null,
          zoneTone: zone,
          buildable: true,
          selectable: true,
          waterfront,
          nodeKey: null,
          nodeType: null,
          opportunityTier: null,
          isCurrentLocation: false,
          roadAxis: null,
          travelOption: null,
          actionTags: [],
          landProfile,
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

  const river: RiverGeometry = {
    controlPoints: RIVER_ANCHORS.map((anchor) => ({
      x: anchor.col * MAP_TILE_SIZE,
      y: anchor.row * MAP_TILE_SIZE,
    })),
    bandPx: RIVER_BAND_PX,
    centerlineSamples: riverCenterlineSamples(),
  };

  return {
    columns: MAP_COLUMNS,
    rows: MAP_ROWS,
    tileSize: MAP_TILE_SIZE,
    worldWidth: WORLD_W,
    worldHeight: WORLD_H,
    districts: DISTRICTS,
    river,
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

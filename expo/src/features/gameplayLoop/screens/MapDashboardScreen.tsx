import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BackHandler, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { DimensionValue } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Path, Rect, Stop } from 'react-native-svg';

import type { MapTileActionTag } from '@/components/gameMap';
import { PlayerStatusBar } from '@/components/gameMap';
import AppBottomNav from '@/components/layout/AppBottomNav';
import SafeAreaPage from '@/components/layout/SafeAreaPage';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { alpha, theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { buildGameplayBottomNavItems } from '@/features/gameplayLoop/navigation';
import JobMarketPanel from '@/features/gameplayLoop/components/JobMarketPanel';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import {
  businessLabel,
  createEmptyBusinessSandboxState,
  defaultGrowthPhaseForBusinessType,
  deriveActiveBusinessProfile,
  getNextGrowthPhase,
} from '@/lib/businessSandbox';
import {
  readBusinessSandboxState,
  updateBusinessSandboxState,
} from '@/lib/businessSandboxPersistence';
import { formatMoney } from '@/lib/gameplayFormatters';
import { openBusiness } from '@/lib/api/business';
import type {
  BusinessLandZoneType,
  BusinessLotSize,
  BusinessSandboxState,
  BusinessTypeKey,
} from '@/types/business';
import type { DailyActionItem, JobMarketJobSnapshot, WorkStateSnapshot } from '@/types/gameplay';

import { useGameplayLoop } from '../context';

type RegionKind = 'suburban' | 'downtown' | 'market' | 'industrial' | 'riverside';

interface WorldRegionPlacement {
  left: DimensionValue;
  top: DimensionValue;
  width: DimensionValue;
  height: DimensionValue;
}

interface BaseDistrictCell {
  id: string;
  row: number;
  col: number;
  title: string;
  subtitle?: string;
}

interface DistrictLotCell extends BaseDistrictCell {
  type: 'lot';
  priceXgp: number;
  size: BusinessLotSize;
  zoneType: BusinessLandZoneType;
  trafficScore: number;
  developmentPotential: number;
}

interface DistrictNodeCell extends BaseDistrictCell {
  type: 'node';
  nodeKind:
    | 'home'
    | 'grocery'
    | 'recovery'
    | 'clinic'
    | 'housing'
    | 'rideshare'
    | 'work'
    | 'job_board'
    | 'business'
    | 'bank'
    | 'stock_center';
  actionTags: MapTileActionTag[];
}

interface DistrictLockedCell extends BaseDistrictCell {
  type: 'locked';
  unlockCopy: string;
}

interface DistrictSceneryCell extends BaseDistrictCell {
  type: 'scenery';
  sceneryKind: 'fountain' | 'park' | 'plaza' | 'waterfront';
}

type DistrictCell = DistrictLotCell | DistrictNodeCell | DistrictLockedCell | DistrictSceneryCell;

interface WorldRegion {
  id: string;
  label: string;
  subtitle: string;
  summary: string;
  kind: RegionKind;
  placement: WorldRegionPlacement;
  unlocked: boolean;
  unlockCopy?: string;
  defaultCellId?: string;
  cells: DistrictCell[];
}

const FALLBACK_NODES = [
  { key: 'home', label: 'Home Base', region: 'Suburban', node_type: 'home', opportunity_tier: 'moderate', is_current_location: true },
  { key: 'job_center', label: 'Job Center', region: 'Downtown', node_type: 'job_board', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'work', label: 'Work Tower', region: 'Downtown', node_type: 'work', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'grocery', label: 'Grocery', region: 'Suburban', node_type: 'grocery', opportunity_tier: 'low', is_current_location: false },
  { key: 'rideshare_hotspot_downtown', label: 'Ride Hub', region: 'Downtown', node_type: 'rideshare_hotspot', opportunity_tier: 'high', is_current_location: false },
  { key: 'rideshare_hotspot_suburban', label: 'Pickup Zone', region: 'Suburban', node_type: 'rideshare_hotspot', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'business_spot', label: 'Business Lane', region: 'Downtown', node_type: 'business', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'bank', label: 'Bank', region: 'Downtown', node_type: 'bank', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'stock_center', label: 'Stock Center', region: 'Downtown', node_type: 'stock_center', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'housing', label: 'Housing Office', region: 'Suburban', node_type: 'housing', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'clinic', label: 'Clinic', region: 'Suburban', node_type: 'clinic', opportunity_tier: 'moderate', is_current_location: false },
] as const;

const SHIFT_FOCUS_OPTIONS = [
  {
    key: 'speed',
    label: 'Push Speed',
    detail: 'Quick clear-out pace and a small XP boost.',
    bonusXp: 4,
  },
  {
    key: 'quality',
    label: 'Protect Quality',
    detail: 'Safer execution with the best XP gain.',
    bonusXp: 6,
  },
  {
    key: 'steady',
    label: 'Steady Pace',
    detail: 'Balanced route with modest but reliable XP.',
    bonusXp: 3,
  },
] as const;

function createLot(
  id: string,
  row: number,
  col: number,
  title: string,
  priceXgp: number,
  trafficScore: number,
  developmentPotential: number,
  size: BusinessLotSize,
  zoneType: BusinessLandZoneType,
  subtitle?: string,
): DistrictLotCell {
  return {
    id,
    type: 'lot',
    row,
    col,
    title,
    subtitle,
    priceXgp,
    size,
    zoneType,
    trafficScore,
    developmentPotential,
  };
}

function createNode(
  id: string,
  row: number,
  col: number,
  title: string,
  subtitle: string,
  nodeKind: DistrictNodeCell['nodeKind'],
  actionTags: MapTileActionTag[],
): DistrictNodeCell {
  return {
    id,
    type: 'node',
    row,
    col,
    title,
    subtitle,
    nodeKind,
    actionTags,
  };
}

function createLocked(
  id: string,
  row: number,
  col: number,
  title: string,
  unlockCopy: string,
): DistrictLockedCell {
  return {
    id,
    type: 'locked',
    row,
    col,
    title,
    subtitle: 'Future district slot',
    unlockCopy,
  };
}

function createScenery(
  id: string,
  row: number,
  col: number,
  title: string,
  subtitle: string,
  sceneryKind: DistrictSceneryCell['sceneryKind'],
): DistrictSceneryCell {
  return {
    id,
    type: 'scenery',
    row,
    col,
    title,
    subtitle,
    sceneryKind,
  };
}

const SUBURBAN_STARTER_CELLS: DistrictCell[] = [
  createNode('home_base', 0, 0, 'Home Base', 'Rest and housing overview.', 'home', []),
  createLot('brook_lot_01', 0, 1, 'Creek Lot', 180, 34, 58, 'medium', 'residential_edge', 'Starter family block.'),
  createNode('grocery_corner', 0, 2, 'Grocery Corner', 'Breakfast and lunch stop.', 'grocery', ['meal_breakfast', 'meal_lunch']),
  createLot('brook_lot_02', 0, 3, 'Corner Lot', 205, 38, 60, 'small', 'residential_edge', 'Near the commuter road.'),
  createNode('rideshare_pickup', 1, 0, 'Pickup Zone', 'Side-income hotspot.', 'rideshare', ['rideshare']),
  createLot('brook_lot_03', 1, 1, 'Roundabout Lot', 212, 42, 64, 'medium', 'residential_edge', 'Reliable commuter traffic.'),
  createNode('pocket_park', 1, 2, 'Pocket Park', 'Low-pressure recovery spot.', 'recovery', ['recovery']),
  createLot('brook_lot_04', 1, 3, 'Garden Lot', 190, 31, 56, 'medium', 'residential_edge', 'Quiet neighborhood parcel.'),
  createNode('clinic_node', 2, 0, 'Clinic', 'Recovery and health services.', 'clinic', []),
  createLot('brook_lot_05', 2, 1, 'School Lot', 228, 41, 66, 'medium', 'residential_edge', 'Strong family demand nearby.'),
  createNode('housing_office', 2, 2, 'Housing Office', 'Rent and move decisions.', 'housing', []),
  createLocked('brook_locked_01', 2, 3, 'Future Brookside Lot', 'Unlock after the next suburban map phase.'),
  createLot('brook_lot_06', 3, 0, 'Bridge Lot', 236, 46, 68, 'medium', 'residential_edge', 'Water-adjacent frontage.'),
  createScenery('brook_fountain', 3, 1, 'Community Fountain', 'Raises neighborhood appeal.', 'fountain'),
  createLot('brook_lot_07', 3, 2, 'Riverbend Lot', 248, 48, 72, 'large', 'residential_edge', 'Premium suburban parcel.'),
  createLot('brook_lot_08', 3, 3, 'Starter Duplex Lot', 172, 30, 54, 'small', 'residential_edge', 'Cheaper first buy.'),
];

const DOWNTOWN_STARTER_CELLS: DistrictCell[] = [
  createNode('work_anchor', 0, 0, 'Work Tower', 'Run your main shift here.', 'work', ['work_shift']),
  createLot('exchange_lot_01', 0, 1, 'Metro Corner', 360, 72, 82, 'small', 'mixed_use', 'High-traffic downtown frontage.'),
  createNode('business_lane', 0, 2, 'Business Lane', 'Open or run your active business.', 'business', ['business_open', 'business_operate', 'business_inventory']),
  createLot('exchange_lot_02', 0, 3, 'Glass Block Lot', 420, 78, 86, 'medium', 'commercial_core', 'Best for premium storefront growth.'),
  createNode('job_center', 1, 0, 'Job Center', 'Switch jobs and start training.', 'job_board', ['job_board']),
  createLot('exchange_lot_03', 1, 1, 'Exchange Lot', 385, 74, 84, 'small', 'mixed_use', 'Balanced downtown lot.'),
  createNode('stock_center', 1, 2, 'Stock Center', 'Future investing lane.', 'stock_center', []),
  createLot('exchange_lot_04', 1, 3, 'Bridge View Lot', 455, 82, 88, 'medium', 'commercial_core', 'Waterfront business frontage.'),
  createLot('exchange_lot_05', 2, 0, 'Harbor Lot', 340, 69, 80, 'small', 'mixed_use', 'Port-adjacent worker demand.'),
  createNode('ride_hub', 2, 1, 'Ride Hub', 'Fast downtown rideshare loop.', 'rideshare', ['rideshare']),
  createLot('exchange_lot_06', 2, 2, 'Core Plaza Lot', 448, 80, 90, 'medium', 'commercial_core', 'Best district prestige.'),
  createNode('bank_node', 2, 3, 'Bank', 'Cash and credit lane.', 'bank', []),
  createLocked('exchange_locked_01', 3, 0, 'Rivergate Tower Lot', 'Unlock after the next downtown map phase.'),
  createLot('exchange_lot_07', 3, 1, 'Executive Lot', 470, 84, 92, 'medium', 'commercial_core', 'Late-game growth lot.'),
  createScenery('exchange_plaza', 3, 2, 'Central Plaza', 'Prestige landmark for this core.', 'plaza'),
  createLot('exchange_lot_08', 3, 3, 'Marina Lot', 410, 76, 85, 'small', 'mixed_use', 'Strong after-work demand.'),
];

const WORLD_REGIONS: WorldRegion[] = [
  {
    id: 'suburban_brookside',
    label: 'Brookside Homes',
    subtitle: 'Starter suburban sector',
    summary: 'Safer entry lots, grocery access, rideshare pickup, and stable family demand.',
    kind: 'suburban',
    placement: { left: '6%', top: '10%', width: '26%', height: '18%' },
    unlocked: true,
    defaultCellId: 'brook_lot_08',
    cells: SUBURBAN_STARTER_CELLS,
  },
  {
    id: 'suburban_lakeview',
    label: 'Lakeview Blocks',
    subtitle: 'Future suburban expansion',
    summary: 'More suburban housing lanes and bigger family lots.',
    kind: 'suburban',
    placement: { left: '56%', top: '8%', width: '28%', height: '18%' },
    unlocked: false,
    unlockCopy: 'Next suburban phase',
    cells: [],
  },
  {
    id: 'downtown_exchange',
    label: 'Exchange Core',
    subtitle: 'Starter downtown sector',
    summary: 'Work tower, job center, business lane, and higher-value mixed-use lots.',
    kind: 'downtown',
    placement: { left: '28%', top: '34%', width: '38%', height: '22%' },
    unlocked: true,
    defaultCellId: 'work_anchor',
    cells: DOWNTOWN_STARTER_CELLS,
  },
  {
    id: 'downtown_rivergate',
    label: 'Rivergate Towers',
    subtitle: 'Future downtown expansion',
    summary: 'Premium offices and prestige lots across the river.',
    kind: 'downtown',
    placement: { left: '63%', top: '56%', width: '18%', height: '16%' },
    unlocked: false,
    unlockCopy: 'Late downtown phase',
    cells: [],
  },
  {
    id: 'market_row',
    label: 'Market Row',
    subtitle: 'Retail district',
    summary: 'Daily commerce and trading lane.',
    kind: 'market',
    placement: { left: '8%', top: '70%', width: '22%', height: '14%' },
    unlocked: false,
    unlockCopy: 'Business milestone',
    cells: [],
  },
  {
    id: 'riverside_grove',
    label: 'Riverside Grove',
    subtitle: 'Leisure and premium housing',
    summary: 'High-appeal riverside property and lighter pressure.',
    kind: 'riverside',
    placement: { left: '32%', top: '76%', width: '20%', height: '12%' },
    unlocked: false,
    unlockCopy: 'Lifestyle milestone',
    cells: [],
  },
  {
    id: 'harbor_works',
    label: 'Harbor Works',
    subtitle: 'Industrial production zone',
    summary: 'Production-heavy district with bigger late-game lots.',
    kind: 'industrial',
    placement: { left: '56%', top: '78%', width: '24%', height: '14%' },
    unlocked: false,
    unlockCopy: 'Industry phase',
    cells: [],
  },
];

function toneForRegion(kind: RegionKind) {
  if (kind === 'downtown') {
    return {
      accent: theme.gameUi.district.downtown.accent,
      surface: alpha(theme.gameUi.district.downtown.base, 0.82),
      muted: alpha(theme.gameUi.district.downtown.accent, 0.12),
    };
  }
  if (kind === 'market') {
    return {
      accent: theme.gameUi.district.commercial.accent,
      surface: alpha(theme.gameUi.district.commercial.base, 0.82),
      muted: alpha(theme.gameUi.district.commercial.accent, 0.12),
    };
  }
  if (kind === 'industrial') {
    return {
      accent: theme.ui.warning,
      surface: alpha(theme.ui.warning, 0.16),
      muted: alpha(theme.ui.warning, 0.1),
    };
  }
  if (kind === 'riverside') {
    return {
      accent: theme.ui.info,
      surface: alpha(theme.ui.info, 0.16),
      muted: alpha(theme.ui.info, 0.1),
    };
  }
  return {
    accent: theme.gameUi.district.suburban.accent,
    surface: alpha(theme.gameUi.district.suburban.base, 0.82),
    muted: alpha(theme.gameUi.district.suburban.accent, 0.12),
  };
}

function regionIcon(kind: RegionKind): keyof typeof MaterialCommunityIcons.glyphMap {
  if (kind === 'downtown') return 'city-variant-outline';
  if (kind === 'market') return 'storefront-outline';
  if (kind === 'industrial') return 'factory';
  if (kind === 'riverside') return 'tree-outline';
  return 'home-city-outline';
}

function nodeIcon(nodeKind: DistrictNodeCell['nodeKind']): keyof typeof MaterialCommunityIcons.glyphMap {
  switch (nodeKind) {
    case 'home':
      return 'home-outline';
    case 'grocery':
      return 'cart-outline';
    case 'recovery':
      return 'tree-outline';
    case 'clinic':
      return 'hospital-box-outline';
    case 'housing':
      return 'office-building-outline';
    case 'rideshare':
      return 'car-outline';
    case 'work':
      return 'briefcase-outline';
    case 'job_board':
      return 'account-search-outline';
    case 'business':
      return 'storefront-outline';
    case 'bank':
      return 'bank-outline';
    default:
      return 'chart-line';
  }
}

function sceneryIcon(kind: DistrictSceneryCell['sceneryKind']): keyof typeof MaterialCommunityIcons.glyphMap {
  if (kind === 'park') return 'tree-outline';
  if (kind === 'waterfront') return 'sail-boat';
  if (kind === 'plaza') return 'fountain';
  return 'fountain';
}

function cellTileKey(regionId: string, cellId: string): string {
  return `${regionId}:${cellId}`;
}

function canonicalMapActionKey(actionKey: string): string {
  const raw = String(actionKey || '').toLowerCase().trim();
  if (!raw) return '';
  if (raw.includes('inventory') || raw.includes('stock')) return 'buy_inventory';
  if (raw.includes('operate') && raw.includes('business')) return 'operate_business';
  if (raw.includes('ride') || raw.includes('delivery') || raw.includes('side_income')) return 'side_income';
  if (raw.includes('work') || raw.includes('shift')) return 'work_shift';
  if (raw.includes('rest') || raw.includes('recover') || raw.includes('watch') || raw.includes('jog')) return 'recovery';
  if (raw.includes('meal') || raw.includes('eat')) return 'eat_meal';
  return raw;
}

function sectionEyebrow(kind: RegionKind): string {
  if (kind === 'downtown') return 'Downtown Sector';
  if (kind === 'market') return 'Retail Sector';
  if (kind === 'industrial') return 'Industrial Sector';
  if (kind === 'riverside') return 'Riverside Sector';
  return 'Suburban Sector';
}

export default function MapDashboardScreen() {
  useScreenTimer('map');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();

  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [openingBusinessType, setOpeningBusinessType] = useState<string | null>(null);
  const [shiftFocusKey, setShiftFocusKey] = useState<(typeof SHIFT_FOCUS_OPTIONS)[number]['key']>('quality');
  const [sandboxBusinessState, setSandboxBusinessState] = useState<BusinessSandboxState>(
    createEmptyBusinessSandboxState(loop.playerId),
  );

  const authState = loop.authoritativeState || loop.dashboard?.authoritative_state || null;
  const workState = (loop.dashboard?.work_state || loop.actionHub?.work_state || null) as WorkStateSnapshot | null;
  const playerStateData = authState?.player_state;
  const cash = Number(playerStateData?.cash ?? loop.dashboard?.stats?.cash_xgp ?? 0);
  const stress = Number(playerStateData?.stress ?? loop.dashboard?.stats?.stress ?? 0);
  const health = Number(playerStateData?.health ?? loop.dashboard?.stats?.health ?? 100);
  const dayNumber = Number(authState?.day_number ?? 1);
  const backendShiftActive = Boolean(workState?.main_shift_active_flag || workState?.is_on_shift);
  const dinnerResolvedToday = Boolean(workState?.dinner_resolved_today);
  const daySettled = Boolean(workState?.day_settled);
  const leisureActivityRunning = loop.dailySession.currentActivity === 'watch_tv';

  useEffect(() => {
    let active = true;
    void readBusinessSandboxState(loop.playerId).then((state) => {
      if (!active) return;
      setSandboxBusinessState(state);
    });
    return () => {
      active = false;
    };
  }, [loop.playerId]);

  const selectedRegion = useMemo(
    () => WORLD_REGIONS.find((region) => region.id === selectedRegionId) || null,
    [selectedRegionId],
  );

  const regionCells = useMemo(
    () => (
      selectedRegion
        ? [...selectedRegion.cells].sort((left, right) => left.row - right.row || left.col - right.col)
        : []
    ),
    [selectedRegion],
  );

  useEffect(() => {
    if (!selectedRegion) {
      setSelectedCellId(null);
      return;
    }
    const defaultCellId = selectedRegion.defaultCellId || regionCells[0]?.id || null;
    setSelectedCellId(defaultCellId);
  }, [regionCells, selectedRegion]);

  const selectedCell = useMemo(
    () => regionCells.find((cell) => cell.id === selectedCellId) || null,
    [regionCells, selectedCellId],
  );

  const ownedLotsByTileKey = useMemo(
    () => new Map(sandboxBusinessState.owned_lots.map((lot) => [lot.tile_key, lot])),
    [sandboxBusinessState.owned_lots],
  );

  const selectedLotOwnership = useMemo(() => {
    if (!selectedRegion || !selectedCell || selectedCell.type !== 'lot') return null;
    return ownedLotsByTileKey.get(cellTileKey(selectedRegion.id, selectedCell.id)) || null;
  }, [ownedLotsByTileKey, selectedCell, selectedRegion]);

  const selectedShiftFocus = useMemo(
    () => SHIFT_FOCUS_OPTIONS.find((option) => option.key === shiftFocusKey) || SHIFT_FOCUS_OPTIONS[1],
    [shiftFocusKey],
  );

  const allActionItems = useMemo(() => {
    if (!loop.actionHub) return [];
    return [
      ...(loop.actionHub.recommended_actions || []),
      ...(loop.actionHub.available_actions || []),
      ...(loop.actionHub.blocked_actions || []),
    ];
  }, [loop.actionHub]);

  const workShiftAction = useMemo(
    () => allActionItems.find((action) => canonicalMapActionKey(String(action.action_key || '')) === 'work_shift') || null,
    [allActionItems],
  );
  const sideIncomeAction = useMemo(
    () => allActionItems.find((action) => canonicalMapActionKey(String(action.action_key || '')) === 'side_income') || null,
    [allActionItems],
  );
  const inventoryAction = useMemo(
    () => allActionItems.find((action) => canonicalMapActionKey(String(action.action_key || '')) === 'buy_inventory') || null,
    [allActionItems],
  );

  const starterOptions = useMemo(
    () => loop.businesses?.starter_options || [
      { business_type: 'fruit_shop', label: 'Fruit Shop', cost_xgp: 500 },
      { business_type: 'food_truck', label: 'Food Truck', cost_xgp: 1200 },
    ],
    [loop.businesses?.starter_options],
  );

  const activeBusiness = useMemo(() => {
    const businesses = loop.businesses?.businesses || [];
    return businesses.find((item) => item.is_active) || null;
  }, [loop.businesses?.businesses]);

  const activeBusinessProfile = useMemo(
    () => deriveActiveBusinessProfile({
      activeBusiness,
      sandboxState: sandboxBusinessState,
      latestProfitXgp: Number(loop.businesses?.profit_snapshot.latest_daily_profit_xgp || 0),
      trailingProfitXgp: Number(loop.businesses?.profit_snapshot.trailing_7d_profit_xgp || 0),
      dayNumber,
    }),
    [
      activeBusiness,
      dayNumber,
      loop.businesses?.profit_snapshot.latest_daily_profit_xgp,
      loop.businesses?.profit_snapshot.trailing_7d_profit_xgp,
      sandboxBusinessState,
    ],
  );

  const persistSandboxState = async (
    updater: (current: BusinessSandboxState) => BusinessSandboxState,
  ) => {
    const next = await updateBusinessSandboxState(loop.playerId, updater);
    setSandboxBusinessState(next);
    return next;
  };

  const openWorldRegion = useCallback((region: WorldRegion) => {
    if (!region.unlocked) {
      loop.setFeedback({
        tone: 'info',
        message: `${region.label} is still locked. ${region.unlockCopy || 'It opens in a later map phase.'}`,
      });
      return;
    }
    setSelectedRegionId(region.id);
  }, [loop]);

  const closeRegion = useCallback(() => {
    setSelectedRegionId(null);
  }, []);

  useFocusEffect(useCallback(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (!selectedRegionId) return false;
      setSelectedRegionId(null);
      return true;
    });
    return () => subscription.remove();
  }, [selectedRegionId]));

  const executeMealFromMap = async (mealType: 'breakfast' | 'lunch' | 'dinner') => {
    if (backendShiftActive) {
      loop.setFeedback({
        tone: 'error',
        message: 'Meals unlock after your shift ends.',
      });
      return;
    }

    if (mealType === 'dinner' && (daySettled || dinnerResolvedToday)) {
      loop.setFeedback({
        tone: 'info',
        message: 'Dinner is already resolved for today.',
      });
      return;
    }

    const mealGuard = loop.dailySession.canStartTimedActivity('eat_meal', { mealType });
    if (!mealGuard.allowed) {
      loop.setFeedback({
        tone: 'error',
        message: mealGuard.reason || 'Meal is unavailable right now.',
      });
      return;
    }

    const ok = await loop.eatMeal(mealType);
    if (ok) {
      const started = loop.dailySession.startTimedActivity('eat_meal', {
        mealType,
        recordHistory: false,
      });
      if (!started.allowed && started.reason) {
        loop.setFeedback({
          tone: 'info',
          message: started.reason,
        });
      }
    }
  };

  const toggleRecoveryFromMap = () => {
    if (backendShiftActive) {
      loop.setFeedback({
        tone: 'error',
        message: 'Leisure spots unlock after your shift ends.',
      });
      return;
    }

    if (leisureActivityRunning) {
      const stopped = loop.dailySession.stopTimedActivity();
      if (!stopped.allowed && stopped.reason) {
        loop.setFeedback({
          tone: 'info',
          message: stopped.reason,
        });
      }
      return;
    }

    const guard = loop.dailySession.canStartTimedActivity('watch_tv');
    if (!guard.allowed) {
      loop.setFeedback({
        tone: 'error',
        message: guard.reason || 'Recovery spot unavailable right now.',
      });
      return;
    }

    loop.dailySession.startTimedActivity('watch_tv');
  };

  const executeMapAction = async (
    action: DailyActionItem | null,
    fallbackMessage: string,
    extraParameters?: Record<string, unknown>,
  ) => {
    if (!action) {
      loop.setFeedback({
        tone: 'error',
        message: fallbackMessage,
      });
      return;
    }
    await loop.executeAction({
      ...action,
      parameters: {
        ...(action.parameters || {}),
        ...(extraParameters || {}),
      },
    });
  };

  const switchToMarketJob = (job: JobMarketJobSnapshot) => {
    const targetJobKey = String(job.job_key || '').trim().toLowerCase();
    if (!targetJobKey) return;
    const action: DailyActionItem = {
      action_key: 'switch_job',
      title: `Switch to ${job.display_name || targetJobKey.replace(/_/g, ' ')}`,
      description: 'Switch main job from the Job Center.',
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'high',
      parameters: {
        new_job_key: targetJobKey,
      },
    };
    void loop.executeAction(action);
  };

  const startMarketTraining = (job: JobMarketJobSnapshot) => {
    const certificationKey = String(job.certification_key || '').trim().toLowerCase();
    if (!certificationKey) return;
    const action: DailyActionItem = {
      action_key: 'start_training',
      title: `Start Training: ${job.certification_name || certificationKey.replace(/_/g, ' ')}`,
      description: 'Begin certification training from the Job Center.',
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'medium',
      parameters: {
        certification_key: certificationKey,
      },
    };
    void loop.executeAction(action);
  };

  const openStarterBusinessFromMap = async (businessType: string) => {
    if (openingBusinessType || !selectedRegion) return;
    setOpeningBusinessType(businessType);
    try {
      const result = await openBusiness(businessType, loop.playerId);
      const label = starterOptions.find((item) => String(item.business_type) === businessType)?.label || businessLabel(businessType);
      await persistSandboxState((current) => ({
        ...current,
        business_market_links: [
          ...current.business_market_links.filter((item) => item.business_id !== result.business_id),
          {
            business_id: result.business_id,
            listing_id: `${selectedRegion.id}:${businessType}`,
            listing_name: label,
            tile_key: null,
            district_key: selectedRegion.id,
            district_label: selectedRegion.label,
            location_label: selectedRegion.label,
            growth_phase_key: defaultGrowthPhaseForBusinessType(businessType),
          },
        ],
      }));
      loop.setFeedback({
        tone: 'success',
        message: `${label} opened successfully in ${selectedRegion.label}.`,
      });
      await loop.refresh({ silent: true });
    } catch (error) {
      const raw = error instanceof Error ? error.message : String(error);
      const friendly = raw.includes('Invalid or expired token')
        ? 'Business session expired. Please refresh and try again.'
        : raw.includes('Not enough cash')
          ? raw
          : 'Could not open this business right now. Please try again.';
      loop.setFeedback({
        tone: 'error',
        message: friendly,
      });
    } finally {
      setOpeningBusinessType((current) => (current === businessType ? null : current));
    }
  };

  const purchaseSelectedLot = async () => {
    if (!selectedRegion || !selectedCell || selectedCell.type !== 'lot' || selectedLotOwnership) return;
    const tileKey = cellTileKey(selectedRegion.id, selectedCell.id);
    await persistSandboxState((current) => ({
      ...current,
      owned_lots: [
        ...current.owned_lots,
        {
          tile_key: tileKey,
          x: selectedCell.col,
          y: selectedCell.row,
          district_key: selectedRegion.id,
          district_label: selectedRegion.label,
          zone_type: selectedCell.zoneType,
          size: selectedCell.size,
          value_xgp: selectedCell.priceXgp,
          purchase_price_xgp: selectedCell.priceXgp,
          traffic_score: selectedCell.trafficScore,
          development_potential: selectedCell.developmentPotential,
          planned_business_type: null,
          placed_business_id: null,
          development_stage: 'land',
          purchased_at: new Date().toISOString(),
        },
      ],
    }));
    loop.setFeedback({
      tone: 'success',
      message: `${selectedCell.title} secured in ${selectedRegion.label}.`,
    });
  };

  const placeActiveBusinessOnLot = async () => {
    if (!selectedRegion || !selectedCell || selectedCell.type !== 'lot' || !selectedLotOwnership || !activeBusiness) return;
    const tileKey = cellTileKey(selectedRegion.id, selectedCell.id);
    await persistSandboxState((current) => ({
      ...current,
      owned_lots: current.owned_lots.map((lot) => {
        if (lot.placed_business_id === activeBusiness.business_id && lot.tile_key !== tileKey) {
          return {
            ...lot,
            planned_business_type: null,
            placed_business_id: null,
            development_stage: 'land',
          };
        }
        if (lot.tile_key !== tileKey) return lot;
        return {
          ...lot,
          planned_business_type: String(activeBusiness.business_type),
          placed_business_id: activeBusiness.business_id,
          development_stage: 'built',
        };
      }),
      business_market_links: [
        ...current.business_market_links.filter((link) => link.business_id !== activeBusiness.business_id),
        {
          business_id: activeBusiness.business_id,
          listing_id: current.business_market_links.find((link) => link.business_id === activeBusiness.business_id)?.listing_id
            || `${selectedRegion.id}:${activeBusiness.business_type}`,
          listing_name: activeBusiness.business_name || businessLabel(activeBusiness.business_type),
          tile_key: tileKey,
          district_key: selectedRegion.id,
          district_label: selectedRegion.label,
          location_label: `${selectedRegion.label} / ${selectedCell.title}`,
          growth_phase_key: current.business_market_links.find((link) => link.business_id === activeBusiness.business_id)?.growth_phase_key
            || defaultGrowthPhaseForBusinessType(String(activeBusiness.business_type)),
        },
      ],
    }));
    loop.setFeedback({
      tone: 'success',
      message: `${activeBusiness.business_name || businessLabel(activeBusiness.business_type)} placed on ${selectedCell.title}.`,
    });
  };

  const advanceActiveBusinessPhase = async () => {
    if (!activeBusinessProfile) return;
    const nextPhase = getNextGrowthPhase(activeBusinessProfile.growth_phase_key);
    if (!nextPhase) return;
    await persistSandboxState((current) => ({
      ...current,
      business_market_links: [
        ...current.business_market_links.filter((link) => link.business_id !== activeBusinessProfile.business_id),
        {
          business_id: activeBusinessProfile.business_id,
          listing_id: current.business_market_links.find((link) => link.business_id === activeBusinessProfile.business_id)?.listing_id
            || `${activeBusinessProfile.district_key || 'region'}:${activeBusinessProfile.business_type}`,
          listing_name: activeBusinessProfile.display_name,
          tile_key: activeBusinessProfile.tile_key,
          district_key: activeBusinessProfile.district_key,
          district_label: activeBusinessProfile.district_label,
          location_label: activeBusinessProfile.location_label,
          growth_phase_key: nextPhase.key,
        },
      ],
    }));
    loop.setFeedback({
      tone: 'success',
      message: `${activeBusinessProfile.display_name} advanced to ${nextPhase.label}.`,
    });
  };

  const selectedRegionOwnedLots = useMemo(
    () => (
      selectedRegion
        ? sandboxBusinessState.owned_lots.filter((lot) => lot.district_key === selectedRegion.id)
        : []
    ),
    [sandboxBusinessState.owned_lots, selectedRegion],
  );

  const regionOwnedCounts = useMemo(
    () => WORLD_REGIONS.reduce<Record<string, number>>((acc, region) => {
      acc[region.id] = sandboxBusinessState.owned_lots.filter((lot) => lot.district_key === region.id).length;
      return acc;
    }, {}),
    [sandboxBusinessState.owned_lots],
  );

  const selectedRegionLotCells = useMemo(
    () => regionCells.filter((cell): cell is DistrictLotCell => cell.type === 'lot'),
    [regionCells],
  );

  const districtAvailableLots = useMemo(
    () => selectedRegionLotCells.filter((cell) => !ownedLotsByTileKey.has(cellTileKey(selectedRegion?.id || '', cell.id))).length,
    [ownedLotsByTileKey, selectedRegion?.id, selectedRegionLotCells],
  );

  const selectedNodeActionTags = selectedCell && selectedCell.type === 'node' ? selectedCell.actionTags : [];
  const jobBoardActive = selectedNodeActionTags.includes('job_board');
  const workNodeActive = selectedNodeActionTags.includes('work_shift');
  const businessNodeActive = selectedNodeActionTags.includes('business_open')
    || selectedNodeActionTags.includes('business_operate')
    || selectedNodeActionTags.includes('business_inventory');
  const canOperateBusiness = Boolean(activeBusiness && selectedNodeActionTags.includes('business_operate'));
  const operatedToday = loop.dailySession.actionsTakenToday.some(
    (entry) => canonicalMapActionKey(String(entry.action_key || '')) === 'operate_business' && entry.success,
  );

  const bottomTabs = useMemo(
    () => buildGameplayBottomNavItems(onboarding.navigateTo),
    [onboarding.navigateTo],
  );

  return (
    <SafeAreaPage edges={['top', 'bottom']} style={styles.page}>
      <View style={styles.root}>
        <PlayerStatusBar
          cash={cash}
          stress={stress}
          health={health}
          dayNumber={dayNumber}
        />

        {loop.feedback ? (
          <View style={[
            styles.feedbackBanner,
            loop.feedback.tone === 'success'
              ? styles.feedbackBannerSuccess
              : loop.feedback.tone === 'error'
                ? styles.feedbackBannerError
                : styles.feedbackBannerInfo,
          ]}>
            <Text style={styles.feedbackText}>{loop.feedback.message}</Text>
            <Pressable onPress={() => loop.setFeedback(null)} hitSlop={10}>
              <MaterialCommunityIcons name="close" size={18} color={theme.ui.text.onDark} />
            </Pressable>
          </View>
        ) : null}

        <View style={styles.mapStage}>
          {selectedRegion ? (
            <ScrollView
              style={styles.scroll}
              contentContainerStyle={styles.districtScrollContent}
              showsVerticalScrollIndicator={false}
            >
              <View style={styles.sectionHeader}>
                <SecondaryButton label="Back To World Map" onPress={closeRegion} />
                <View style={styles.sectionHeaderCopy}>
                  <Text style={styles.sectionEyebrow}>{sectionEyebrow(selectedRegion.kind)}</Text>
                  <Text style={styles.sectionTitle}>{selectedRegion.label}</Text>
                  <Text style={styles.sectionSubtitle}>{selectedRegion.summary}</Text>
                </View>
              </View>

              <View style={styles.summaryRow}>
                <MetricPill label="Owned lots" value={String(selectedRegionOwnedLots.length)} />
                <MetricPill label="Available lots" value={String(districtAvailableLots)} />
                <MetricPill label="Cash" value={formatMoney(cash)} />
              </View>

              <View style={styles.districtBoard}>
                {regionCells.map((cell) => {
                  const isSelected = selectedCell?.id === cell.id;
                  const tone = toneForRegion(selectedRegion.kind);
                  const ownership = cell.type === 'lot'
                    ? ownedLotsByTileKey.get(cellTileKey(selectedRegion.id, cell.id)) || null
                    : null;
                  return (
                    <Pressable
                      key={cell.id}
                      onPress={() => setSelectedCellId(cell.id)}
                      style={[
                        styles.gridCell,
                        { backgroundColor: tone.muted, borderColor: alpha(theme.ui.border, 0.44) },
                        cell.type === 'node' ? styles.gridCellNode : null,
                        cell.type === 'scenery' ? styles.gridCellScenery : null,
                        cell.type === 'locked' ? styles.gridCellLocked : null,
                        cell.type === 'lot' && !ownership ? styles.gridCellLotOpen : null,
                        ownership ? styles.gridCellOwned : null,
                        ownership?.placed_business_id ? styles.gridCellBuilt : null,
                        isSelected ? { borderColor: tone.accent, backgroundColor: alpha(tone.accent, 0.18) } : null,
                      ]}
                    >
                      {cell.type === 'node' ? (
                        <>
                          <MaterialCommunityIcons name={nodeIcon(cell.nodeKind)} size={20} color={tone.accent} />
                          <Text style={styles.gridNodeTitle}>{cell.title}</Text>
                          <Text style={styles.gridNodeMeta}>Open</Text>
                        </>
                      ) : cell.type === 'lot' ? (
                        <>
                          <Text style={styles.gridLotStatus}>
                            {ownership?.placed_business_id
                              ? 'Built'
                              : ownership
                                ? 'Owned'
                                : 'Buy'}
                          </Text>
                          <Text style={styles.gridLotPrice}>
                            {ownership
                              ? (ownership.placed_business_id ? 'Active Site' : 'Held Land')
                              : formatMoney(cell.priceXgp)}
                          </Text>
                        </>
                      ) : cell.type === 'locked' ? (
                        <>
                          <MaterialCommunityIcons name="lock-outline" size={20} color={theme.ui.warning} />
                          <Text style={styles.gridLockedTitle}>Locked</Text>
                          <Text style={styles.gridLockedMeta}>Later</Text>
                        </>
                      ) : (
                        <>
                          <MaterialCommunityIcons name={sceneryIcon(cell.sceneryKind)} size={18} color={theme.ui.info} />
                          <Text style={styles.gridNodeTitle}>{cell.title}</Text>
                        </>
                      )}
                    </Pressable>
                  );
                })}
              </View>

              {selectedCell ? (
                <View style={styles.detailCard}>
                  <View style={styles.detailHeader}>
                    <View style={styles.detailHeaderCopy}>
                      <Text style={styles.detailEyebrow}>Selected Area</Text>
                      <Text style={styles.detailTitle}>{selectedCell.title}</Text>
                      <Text style={styles.detailSubtitle}>{selectedCell.subtitle || 'Inspect this district surface.'}</Text>
                    </View>
                    <View style={[styles.detailBadge, { borderColor: alpha(toneForRegion(selectedRegion.kind).accent, 0.36) }]}>
                      <Text style={styles.detailBadgeText}>
                        {selectedCell.type === 'node'
                          ? 'Node'
                          : selectedCell.type === 'lot'
                            ? selectedLotOwnership?.placed_business_id
                              ? 'Built'
                              : selectedLotOwnership
                                ? 'Owned'
                                : 'Lot'
                            : selectedCell.type === 'locked'
                              ? 'Locked'
                              : 'Scenery'}
                      </Text>
                    </View>
                  </View>

                  {selectedCell.type === 'lot' ? (
                    <>
                      <View style={styles.summaryRow}>
                        <MetricPill label="Price" value={formatMoney(selectedCell.priceXgp)} />
                        <MetricPill label="Traffic" value={`${selectedCell.trafficScore}/100`} />
                        <MetricPill label="Dev" value={`${selectedCell.developmentPotential}/100`} />
                      </View>
                      <View style={styles.summaryRow}>
                        <MetricPill label="Zone" value={selectedCell.zoneType.replace(/_/g, ' ')} />
                        <MetricPill label="Size" value={selectedCell.size} />
                        <MetricPill label="District" value={selectedRegion.label} />
                      </View>

                      {selectedLotOwnership ? (
                        <View style={styles.selectionStack}>
                          <Text style={styles.supportingCopy}>
                            {selectedLotOwnership.placed_business_id
                              ? 'This lot already hosts your active business footprint.'
                              : 'This land is owned and ready for development.'}
                          </Text>
                          {selectedLotOwnership.placed_business_id ? (
                            <SecondaryButton label="Business Placed" disabled />
                          ) : activeBusiness ? (
                            <PrimaryButton
                              label={`Place ${activeBusinessProfile?.growth_phase_label || businessLabel(activeBusiness.business_type)} Here`}
                              onPress={() => { void placeActiveBusinessOnLot(); }}
                            />
                          ) : (
                            <SecondaryButton label="Open A Business First" disabled />
                          )}
                        </View>
                      ) : (
                        <View style={styles.selectionStack}>
                          <Text style={styles.supportingCopy}>
                            Secure this lot now, then place your active business later when you are ready to expand.
                          </Text>
                          <PrimaryButton
                            label={`Purchase ${formatMoney(selectedCell.priceXgp)}`}
                            onPress={() => { void purchaseSelectedLot(); }}
                          />
                        </View>
                      )}
                    </>
                  ) : null}

                  {selectedCell.type === 'node' ? (
                    <View style={styles.selectionStack}>
                      {workNodeActive ? (
                        <>
                          <Text style={styles.actionSectionTitle}>Shift Focus</Text>
                          <View style={styles.focusChipRow}>
                            {SHIFT_FOCUS_OPTIONS.map((option) => {
                              const selected = option.key === selectedShiftFocus.key;
                              return (
                                <Pressable
                                  key={option.key}
                                  onPress={() => setShiftFocusKey(option.key)}
                                  style={[
                                    styles.focusChip,
                                    selected ? { borderColor: toneForRegion(selectedRegion.kind).accent, backgroundColor: alpha(toneForRegion(selectedRegion.kind).accent, 0.14) } : null,
                                  ]}
                                >
                                  <Text style={[styles.focusChipTitle, selected ? styles.focusChipTitleActive : null]}>{option.label}</Text>
                                  <Text style={styles.focusChipMeta}>+{option.bonusXp} XP</Text>
                                </Pressable>
                              );
                            })}
                          </View>
                          <PrimaryButton
                            label={workShiftAction?.title || 'Start Shift'}
                            disabled={!workShiftAction || loop.executingAction || loop.dailySession.canExecuteAction(workShiftAction).allowed === false}
                            onPress={() => {
                              void executeMapAction(
                                workShiftAction,
                                'No work shift is available right now.',
                                { shift_focus: selectedShiftFocus.key },
                              );
                            }}
                          />
                          <Text style={styles.supportingCopy}>{selectedShiftFocus.detail}</Text>
                        </>
                      ) : null}

                      {selectedNodeActionTags.includes('meal_breakfast') ? (
                        <PrimaryButton
                          label="Buy Breakfast"
                          disabled={loop.executingAction || cash < 6}
                          onPress={() => { void executeMealFromMap('breakfast'); }}
                        />
                      ) : null}

                      {selectedNodeActionTags.includes('meal_lunch') ? (
                        <SecondaryButton
                          label="Buy Lunch"
                          disabled={loop.executingAction || cash < 6}
                          onPress={() => { void executeMealFromMap('lunch'); }}
                        />
                      ) : null}

                      {selectedNodeActionTags.includes('rideshare') ? (
                        <PrimaryButton
                          label="Run 1 Ride"
                          disabled={!sideIncomeAction || loop.executingAction || loop.dailySession.canExecuteAction(sideIncomeAction).allowed === false}
                          onPress={() => { void executeMapAction(sideIncomeAction, 'Rideshare is not available right now.'); }}
                        />
                      ) : null}

                      {selectedNodeActionTags.includes('recovery') ? (
                        <SecondaryButton
                          label={leisureActivityRunning ? 'Stop Leisure' : 'Relax Here'}
                          disabled={loop.executingAction}
                          onPress={toggleRecoveryFromMap}
                        />
                      ) : null}

                      {businessNodeActive ? (
                        <>
                          {activeBusinessProfile ? (
                            <View style={styles.businessPanel}>
                              <Text style={styles.actionSectionTitle}>Active Business</Text>
                              <View style={styles.summaryRow}>
                                <MetricPill label="Business" value={activeBusinessProfile.growth_phase_label} />
                                <MetricPill label="Traffic" value={`${activeBusinessProfile.traffic_score}/100`} />
                                <MetricPill label="Demand" value={`${activeBusinessProfile.demand_score}/100`} />
                              </View>
                              <Text style={styles.supportingCopy}>
                                {activeBusinessProfile.display_name} is anchored at {activeBusinessProfile.location_label}.
                              </Text>
                              <PrimaryButton
                                label={canOperateBusiness
                                  ? (operatedToday ? 'Operated Today' : 'Run Business')
                                  : 'Business Unavailable'}
                                disabled={!canOperateBusiness || operatedToday || loop.dailySession.sessionStatus !== 'active'}
                                onPress={() => { void loop.operateBusiness(); }}
                              />
                              <SecondaryButton
                                label="Restock Inventory"
                                disabled={!inventoryAction || loop.executingAction || loop.dailySession.canExecuteAction(inventoryAction).allowed === false}
                                onPress={() => { void executeMapAction(inventoryAction, 'Inventory restock is unavailable right now.'); }}
                              />
                              {getNextGrowthPhase(activeBusinessProfile.growth_phase_key) ? (
                                <SecondaryButton
                                  label={`Advance To ${getNextGrowthPhase(activeBusinessProfile.growth_phase_key)?.label || 'Next Phase'}`}
                                  onPress={() => { void advanceActiveBusinessPhase(); }}
                                />
                              ) : null}
                            </View>
                          ) : (
                            <View style={styles.businessPanel}>
                              <Text style={styles.actionSectionTitle}>Starter Businesses</Text>
                              <Text style={styles.supportingCopy}>
                                Open one starter business, then place it onto any owned lot in this district or another unlocked district.
                              </Text>
                              {starterOptions.map((option, index) => {
                                const need = Math.max(Number(option.cost_xgp || 0) - cash, 0);
                                const buttonLabel = need > 0
                                  ? `${option.label} (${formatMoney(need)} short)`
                                  : `Open ${option.label}`;
                                return index === 0 ? (
                                  <PrimaryButton
                                    key={option.business_type}
                                    label={buttonLabel}
                                    disabled={Boolean(openingBusinessType) || need > 0}
                                    onPress={() => { void openStarterBusinessFromMap(String(option.business_type)); }}
                                  />
                                ) : (
                                  <SecondaryButton
                                    key={option.business_type}
                                    label={buttonLabel}
                                    disabled={Boolean(openingBusinessType) || need > 0}
                                    onPress={() => { void openStarterBusinessFromMap(String(option.business_type)); }}
                                  />
                                );
                              })}
                            </View>
                          )}
                        </>
                      ) : null}

                      {jobBoardActive ? (
                        <JobMarketPanel
                          jobMarket={workState?.job_market || null}
                          executingAction={loop.executingAction}
                          busyActionKey={loop.busyActionKey}
                          onSwitchJob={switchToMarketJob}
                          onStartTraining={startMarketTraining}
                        />
                      ) : null}

                      {!workNodeActive
                        && !selectedNodeActionTags.includes('meal_breakfast')
                        && !selectedNodeActionTags.includes('meal_lunch')
                        && !selectedNodeActionTags.includes('rideshare')
                        && !selectedNodeActionTags.includes('recovery')
                        && !businessNodeActive
                        && !jobBoardActive ? (
                          <Text style={styles.supportingCopy}>
                            This landmark is part of the district identity now. More direct actions can be connected here in the next map phase.
                          </Text>
                        ) : null}
                    </View>
                  ) : null}

                  {selectedCell.type === 'locked' ? (
                    <Text style={styles.supportingCopy}>{selectedCell.unlockCopy}</Text>
                  ) : null}

                  {selectedCell.type === 'scenery' ? (
                    <Text style={styles.supportingCopy}>
                      This landmark improves the feel of the district and helps the submap feel like a place, not just a purchase grid.
                    </Text>
                  ) : null}
                </View>
              ) : null}
            </ScrollView>
          ) : (
            <ScrollView
              style={styles.scroll}
              contentContainerStyle={styles.worldScrollContent}
              showsVerticalScrollIndicator={false}
            >
              <View style={styles.sectionHeader}>
                <View style={styles.sectionHeaderCopy}>
                  <Text style={styles.sectionEyebrow}>Main World Map</Text>
                  <Text style={styles.sectionTitle}>District Expansion Map</Text>
                  <Text style={styles.sectionSubtitle}>
                    Start with one suburban area and one downtown area. Tap an unlocked region to open its submap.
                  </Text>
                </View>
              </View>

              <View style={styles.summaryRow}>
                <MetricPill label="Unlocked now" value="2 regions" />
                <MetricPill label="Starter path" value="Suburban + Downtown" />
                <MetricPill label="Cash" value={formatMoney(cash)} />
              </View>

              <View style={styles.worldMapBoard}>
                <Svg style={StyleSheet.absoluteFillObject} viewBox="0 0 100 100" preserveAspectRatio="none">
                  <Defs>
                    <LinearGradient id="mapGrass" x1="0" y1="0" x2="1" y2="1">
                      <Stop offset="0%" stopColor={alpha(theme.gameUi.success, 0.28)} />
                      <Stop offset="100%" stopColor={alpha(theme.gameUi.success, 0.1)} />
                    </LinearGradient>
                    <LinearGradient id="mapRiver" x1="0" y1="0" x2="0" y2="1">
                      <Stop offset="0%" stopColor={alpha(theme.ui.info, 0.85)} />
                      <Stop offset="100%" stopColor={alpha(theme.gameUi.primary, 0.95)} />
                    </LinearGradient>
                  </Defs>
                  <Rect x="0" y="0" width="100" height="100" rx="6" fill="url(#mapGrass)" />
                  <Path
                    d="M 55 2 C 62 14, 49 22, 53 34 C 57 48, 72 57, 66 71 C 61 83, 44 89, 47 98"
                    stroke={alpha(theme.ui.info, 0.18)}
                    strokeWidth="14"
                    strokeLinecap="round"
                    fill="none"
                  />
                  <Path
                    d="M 55 2 C 62 14, 49 22, 53 34 C 57 48, 72 57, 66 71 C 61 83, 44 89, 47 98"
                    stroke="url(#mapRiver)"
                    strokeWidth="9"
                    strokeLinecap="round"
                    fill="none"
                  />
                  <Path
                    d="M 8 22 L 42 40 L 74 31"
                    stroke={alpha(theme.ui.border, 0.72)}
                    strokeWidth="2.6"
                    strokeLinecap="round"
                    fill="none"
                  />
                  <Path
                    d="M 16 67 L 40 58 L 68 83"
                    stroke={alpha(theme.ui.border, 0.72)}
                    strokeWidth="2.6"
                    strokeLinecap="round"
                    fill="none"
                  />
                  <Path
                    d="M 26 14 L 36 78"
                    stroke={alpha(theme.ui.border, 0.54)}
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    fill="none"
                  />
                  <Path
                    d="M 68 10 L 62 80"
                    stroke={alpha(theme.ui.border, 0.54)}
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    fill="none"
                  />
                  <Circle cx="46" cy="43" r="9" fill={alpha(theme.ui.action, 0.16)} />
                  <Circle cx="46" cy="43" r="5.8" fill={alpha(theme.ui.action, 0.24)} />
                </Svg>

                <View style={styles.worldCityCluster}>
                  <View style={[styles.worldTower, styles.worldTowerTall]} />
                  <View style={[styles.worldTower, styles.worldTowerMid]} />
                  <View style={[styles.worldTower, styles.worldTowerWide]} />
                  <View style={[styles.worldTower, styles.worldTowerSmall]} />
                </View>

                {WORLD_REGIONS.map((region) => {
                  const tone = toneForRegion(region.kind);
                  const ownedCount = regionOwnedCounts[region.id] || 0;
                  return (
                    <Pressable
                      key={region.id}
                      onPress={() => openWorldRegion(region)}
                      disabled={!region.unlocked}
                      style={({ pressed }) => [
                        styles.worldRegionCard,
                        region.placement,
                        {
                          backgroundColor: region.unlocked ? alpha(theme.ui.bg.card, 0.94) : alpha(theme.ui.bg.cardRaised, 0.88),
                          borderColor: region.unlocked ? alpha(tone.accent, 0.44) : alpha(theme.ui.border, 0.34),
                        },
                        pressed && region.unlocked ? styles.worldRegionCardPressed : null,
                      ]}
                    >
                      <View style={styles.worldRegionHead}>
                        <View style={[styles.worldRegionIconWrap, { backgroundColor: alpha(tone.accent, 0.12) }]}>
                          <MaterialCommunityIcons
                            name={region.unlocked ? regionIcon(region.kind) : 'lock-outline'}
                            size={18}
                            color={region.unlocked ? tone.accent : theme.ui.text.onDarkMuted}
                          />
                        </View>
                        <View style={styles.worldRegionCopy}>
                          <Text style={styles.worldRegionTitle}>{region.label}</Text>
                          <Text style={styles.worldRegionSubtitle}>{region.subtitle}</Text>
                        </View>
                      </View>
                      <Text style={styles.worldRegionMeta}>
                        {region.unlocked
                          ? (ownedCount > 0 ? `Owned lots ${ownedCount}` : 'Open submap')
                          : (region.unlockCopy || 'Locked')}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </ScrollView>
          )}
        </View>

        <AppBottomNav items={bottomTabs} activeKey="map" />
      </View>
    </SafeAreaPage>
  );
}

function MetricPill({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <View style={styles.metricPill}>
      <Text style={styles.metricPillLabel}>{label}</Text>
      <Text style={styles.metricPillValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {
    backgroundColor: theme.gameUi.background,
  },
  root: {
    flex: 1,
    backgroundColor: theme.gameUi.background,
  },
  feedbackBanner: {
    marginHorizontal: theme.spacing.md,
    marginTop: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  feedbackBannerSuccess: {
    backgroundColor: alpha(theme.ui.positive, 0.18),
    borderColor: alpha(theme.ui.positive, 0.42),
  },
  feedbackBannerError: {
    backgroundColor: alpha(theme.ui.danger, 0.18),
    borderColor: alpha(theme.ui.danger, 0.42),
  },
  feedbackBannerInfo: {
    backgroundColor: alpha(theme.ui.info, 0.18),
    borderColor: alpha(theme.ui.info, 0.42),
  },
  feedbackText: {
    flex: 1,
    ...theme.typography.bodySm,
    color: theme.ui.text.onDark,
    fontWeight: '700',
  },
  mapStage: {
    flex: 1,
  },
  scroll: {
    flex: 1,
  },
  worldScrollContent: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
    gap: theme.spacing.md,
  },
  districtScrollContent: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
    gap: theme.spacing.md,
  },
  sectionHeader: {
    gap: theme.spacing.sm,
  },
  sectionHeaderCopy: {
    gap: theme.spacing.xxs,
  },
  sectionEyebrow: {
    ...theme.typography.caption,
    color: theme.ui.info,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  sectionTitle: {
    ...theme.typography.headingLg,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  sectionSubtitle: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  summaryRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  metricPill: {
    minWidth: 104,
    flexGrow: 1,
    borderRadius: theme.radius.lg,
    backgroundColor: alpha(theme.ui.bg.cardRaised, 0.95),
    borderWidth: 1,
    borderColor: alpha(theme.ui.border, 0.32),
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: 2,
  },
  metricPillLabel: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    fontWeight: '700',
  },
  metricPillValue: {
    ...theme.typography.bodyMd,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  worldMapBoard: {
    position: 'relative',
    height: 620,
    borderRadius: theme.radius.xl,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: alpha(theme.ui.border, 0.3),
    backgroundColor: alpha(theme.ui.bg.cardRaised, 0.96),
  },
  worldCityCluster: {
    position: 'absolute',
    left: '38%',
    top: '38%',
    width: '22%',
    height: '16%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  worldTower: {
    position: 'absolute',
    bottom: 0,
    borderRadius: 10,
    backgroundColor: alpha(theme.ui.bg.card, 0.95),
    borderWidth: 1,
    borderColor: alpha(theme.ui.border, 0.36),
  },
  worldTowerTall: {
    width: 26,
    height: 88,
    left: 46,
  },
  worldTowerMid: {
    width: 24,
    height: 72,
    left: 20,
  },
  worldTowerWide: {
    width: 34,
    height: 62,
    left: 76,
  },
  worldTowerSmall: {
    width: 20,
    height: 48,
    left: 6,
  },
  worldRegionCard: {
    position: 'absolute',
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    justifyContent: 'space-between',
    minHeight: 94,
    ...theme.shadow.md,
  },
  worldRegionCardPressed: {
    opacity: 0.92,
    transform: [{ scale: 0.98 }],
  },
  worldRegionHead: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: theme.spacing.sm,
  },
  worldRegionIconWrap: {
    width: 34,
    height: 34,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  worldRegionCopy: {
    flex: 1,
    gap: 2,
  },
  worldRegionTitle: {
    ...theme.typography.bodyMd,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  worldRegionSubtitle: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '700',
  },
  worldRegionMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '700',
  },
  districtBoard: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  gridCell: {
    width: '23%',
    aspectRatio: 1,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    padding: theme.spacing.sm,
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  gridCellNode: {
    backgroundColor: alpha(theme.ui.bg.card, 0.96),
  },
  gridCellScenery: {
    backgroundColor: alpha(theme.ui.info, 0.08),
    justifyContent: 'center',
    alignItems: 'center',
    gap: theme.spacing.xs,
  },
  gridCellLocked: {
    backgroundColor: alpha(theme.ui.bg.cardRaised, 0.88),
  },
  gridCellLotOpen: {
    backgroundColor: alpha(theme.ui.positive, 0.08),
  },
  gridCellOwned: {
    backgroundColor: alpha(theme.ui.info, 0.1),
  },
  gridCellBuilt: {
    backgroundColor: alpha(theme.ui.warning, 0.12),
  },
  gridNodeTitle: {
    ...theme.typography.caption,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  gridNodeMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
  gridLotStatus: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  gridLotPrice: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  gridLockedTitle: {
    ...theme.typography.caption,
    color: theme.ui.warning,
    fontWeight: '800',
  },
  gridLockedMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
  detailCard: {
    borderRadius: theme.radius.xl,
    backgroundColor: alpha(theme.ui.bg.card, 0.98),
    borderWidth: 1,
    borderColor: alpha(theme.ui.border, 0.3),
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  detailHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  detailHeaderCopy: {
    flex: 1,
    gap: 2,
  },
  detailEyebrow: {
    ...theme.typography.caption,
    color: theme.ui.info,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  detailTitle: {
    ...theme.typography.headingSm,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  detailSubtitle: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  detailBadge: {
    borderRadius: 999,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 7,
    borderWidth: 1,
    backgroundColor: alpha(theme.ui.bg.cardRaised, 0.96),
  },
  detailBadgeText: {
    ...theme.typography.caption,
    color: theme.ui.text.onDark,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  selectionStack: {
    gap: theme.spacing.sm,
  },
  actionSectionTitle: {
    ...theme.typography.caption,
    color: theme.ui.info,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  supportingCopy: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  focusChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  focusChip: {
    minWidth: 96,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    borderColor: alpha(theme.ui.border, 0.36),
    backgroundColor: alpha(theme.ui.bg.cardRaised, 0.96),
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: 2,
  },
  focusChipTitle: {
    ...theme.typography.caption,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  focusChipTitleActive: {
    color: theme.ui.info,
  },
  focusChipMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '700',
  },
  businessPanel: {
    gap: theme.spacing.sm,
    borderRadius: theme.radius.lg,
    backgroundColor: alpha(theme.ui.bg.cardRaised, 0.94),
    borderWidth: 1,
    borderColor: alpha(theme.ui.border, 0.28),
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
  },
});

import { useFocusEffect } from '@react-navigation/native';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BackHandler, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  GameMap,
  MapDetailSheet,
  PlayerStatusBar,
  buildSandboxCityMap,
  describeTileKind,
} from '@/components/gameMap';
import type {
  MapNode,
  MapTileActionTag,
  SandboxMapTile,
} from '@/components/gameMap';
import SafeAreaPage from '@/components/layout/SafeAreaPage';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import type { OnboardingRouteKey } from '@/features/onboarding/context';
import BusinessMarketPanel from '@/features/gameplayLoop/components/BusinessMarketPanel';
import JobMarketPanel from '@/features/gameplayLoop/components/JobMarketPanel';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import {
  businessLabel,
  createEmptyBusinessSandboxState,
  deriveActiveBusinessProfile,
  deriveBusinessMarketListings,
  describeLotSize,
  describeZoneType,
  getNextGrowthPhase,
} from '@/lib/businessSandbox';
import {
  readBusinessSandboxState,
  updateBusinessSandboxState,
} from '@/lib/businessSandboxPersistence';
import { formatMoney } from '@/lib/gameplayFormatters';
import { openBusiness } from '@/lib/api/business';
import type { BusinessMarketListing, BusinessSandboxState } from '@/types/business';
import type { DailyActionItem, JobMarketJobSnapshot, WorkStateSnapshot } from '@/types/gameplay';

import { useGameplayLoop } from '../context';

const FALLBACK_NODES: MapNode[] = [
  { key: 'home', label: 'Home', region: 'Suburban', node_type: 'home', opportunity_tier: 'moderate', is_current_location: true },
  { key: 'job_center', label: 'Job Center', region: 'Downtown', node_type: 'job_board', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'work', label: 'Work', region: 'Downtown', node_type: 'work', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'grocery', label: 'Grocery', region: 'Suburban', node_type: 'grocery', opportunity_tier: 'low', is_current_location: false },
  { key: 'rideshare_hotspot_downtown', label: 'Rideshare Hub', region: 'Downtown', node_type: 'rideshare_hotspot', opportunity_tier: 'high', is_current_location: false },
  { key: 'rideshare_hotspot_suburban', label: 'Pickup Zone', region: 'Suburban', node_type: 'rideshare_hotspot', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'business_spot', label: 'Business', region: 'Downtown', node_type: 'business', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'bank', label: 'Bank', region: 'Downtown', node_type: 'bank', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'stock_center', label: 'Stock Center', region: 'Downtown', node_type: 'stock_center', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'certification_school', label: 'Certification School', region: 'Downtown', node_type: 'certification_school', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'housing', label: 'Housing Office', region: 'Suburban', node_type: 'housing', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'clinic', label: 'Clinic', region: 'Suburban', node_type: 'clinic', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'gas_station', label: 'Gas Station', region: 'Suburban', node_type: 'gas_station', opportunity_tier: 'low', is_current_location: false },
  { key: 'car_sale', label: 'Car Dealership', region: 'Downtown', node_type: 'car_sale', opportunity_tier: 'moderate', is_current_location: false },
];

const SHIFT_FOCUS_OPTIONS = [
  {
    key: 'speed',
    label: 'Push Speed',
    detail: 'Light quick-action choice. Small XP bonus for moving product fast.',
    bonusXp: 4,
  },
  {
    key: 'quality',
    label: 'Protect Quality',
    detail: 'Light management choice. Best XP gain for careful execution.',
    bonusXp: 6,
  },
  {
    key: 'steady',
    label: 'Steady Pace',
    detail: 'Keep output stable and still lock in a modest bonus.',
    bonusXp: 3,
  },
] as const;

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

interface TileActionButton {
  key: string;
  label: string;
  detail: string;
  variant: 'primary' | 'secondary';
  disabled: boolean;
  onPress: () => void;
}

function marketLinkIdForBusiness(
  state: BusinessSandboxState,
  businessId: string,
  fallbackListingId: string,
): string {
  return state.business_market_links.find((item) => item.business_id === businessId)?.listing_id
    || fallbackListingId
    || `owned_${businessId}`;
}

function formatMapNodeType(nodeType: string | null | undefined): string {
  const raw = String(nodeType || '').trim();
  if (!raw) return '';
  return raw
    .split('_')
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ');
}

function selectedTileModeLabel(
  tile: SandboxMapTile | null,
  ownedLot: BusinessSandboxState['owned_lots'][number] | null,
): string {
  if (!tile) return 'Browse Mode';
  if (ownedLot?.placed_business_id) return 'Owned Business';
  if (ownedLot) return 'Owned Lot';

  switch (tile.kind) {
    case 'empty_lot':
      return 'Land';
    case 'building_slot':
      return 'Building Slot';
    case 'existing_business':
      return 'Business';
    case 'service_building':
      return 'Service';
    case 'expansion_node':
      return 'Expansion';
    case 'road':
      return 'Road';
    default:
      return describeTileKind(tile.kind);
  }
}

function selectedTileStatusLabel(
  tile: SandboxMapTile | null,
  ownedLot: BusinessSandboxState['owned_lots'][number] | null,
): string {
  if (!tile) return 'Tap a slot to inspect it.';
  if (tile.isCurrentLocation) return 'You are here';
  if (ownedLot?.placed_business_id) return 'Operating site';
  if (ownedLot) return 'Ready for development';
  if (tile.travelOption) return 'Travel to interact';
  if (tile.buildable) return 'Build-ready';
  return 'Scout / inspect';
}

export default function MapDashboardScreen() {
  useScreenTimer('map');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();

  const [zoomLevel, setZoomLevel] = useState(1);
  const [selectedTileKey, setSelectedTileKey] = useState<string | null>(null);
  const [openingBusinessType, setOpeningBusinessType] = useState<string | null>(null);
  const [shiftFocusKey, setShiftFocusKey] = useState<(typeof SHIFT_FOCUS_OPTIONS)[number]['key']>('quality');
  const [sandboxBusinessState, setSandboxBusinessState] = useState<BusinessSandboxState>(
    createEmptyBusinessSandboxState(loop.playerId),
  );
  const [selectedListingId, setSelectedListingId] = useState<string | null>(null);
  const [comparedListingIds, setComparedListingIds] = useState<string[]>([]);

  const authState = loop.authoritativeState || loop.dashboard?.authoritative_state || null;
  const workState = (loop.dashboard?.work_state || loop.actionHub?.work_state || null) as WorkStateSnapshot | null;
  const cityMap = workState?.city_map || null;

  const playerStateData = authState?.player_state;
  const cash = Number(playerStateData?.cash ?? loop.dashboard?.stats?.cash_xgp ?? 0);
  const stress = Number(playerStateData?.stress ?? loop.dashboard?.stats?.stress ?? 0);
  const health = Number(playerStateData?.health ?? loop.dashboard?.stats?.health ?? 100);
  const dayNumber = Number(authState?.day_number ?? 1);

  const currentLocationKey = String(
    workState?.current_location_key
    || cityMap?.current_location_key
    || 'home',
  );
  const currentLocationLabel = String(
    workState?.current_location_label
    || cityMap?.current_location_label
    || 'Home',
  );

  const backendShiftActive = Boolean(workState?.main_shift_active_flag || workState?.is_on_shift);
  const dinnerResolvedToday = Boolean(workState?.dinner_resolved_today);
  const daySettled = Boolean(workState?.day_settled);
  const leisureActivityRunning = loop.dailySession.currentActivity === 'watch_tv';

  const nodes: MapNode[] = useMemo(() => {
    const rawNodes = cityMap?.nodes;
    if (Array.isArray(rawNodes) && rawNodes.length > 0) {
      return rawNodes.map((n) => ({
        key: String(n.key || ''),
        label: String(n.label || ''),
        region: String(n.region || 'Suburban'),
        node_type: String(n.node_type || ''),
        opportunity_tier: String(n.opportunity_tier || 'moderate'),
        is_current_location: Boolean(n.is_current_location),
      }));
    }
    return FALLBACK_NODES;
  }, [cityMap]);

  const travelOptions = useMemo(
    () => (
      (workState?.travel_options && workState.travel_options.length > 0
        ? workState.travel_options
        : cityMap?.travel_options)
      || []
    ),
    [cityMap?.travel_options, workState?.travel_options],
  );

  const sandboxMap = useMemo(
    () => buildSandboxCityMap({
      nodes,
      travelOptions,
      currentLocationKey,
    }),
    [currentLocationKey, nodes, travelOptions],
  );

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

  useEffect(() => {
    if (selectedTileKey && !sandboxMap.tileByKey[selectedTileKey]) {
      setSelectedTileKey(null);
    }
  }, [sandboxMap, selectedTileKey]);

  const selectedTile = selectedTileKey ? sandboxMap.tileByKey[selectedTileKey] || null : null;
  const selectedDistrict = selectedTile?.districtKey
    ? sandboxMap.districts.find((district) => district.key === selectedTile.districtKey) || null
    : null;
  const detailSheetOpen = Boolean(selectedTile);

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
  const selectedShiftFocus = useMemo(
    () => SHIFT_FOCUS_OPTIONS.find((option) => option.key === shiftFocusKey) || SHIFT_FOCUS_OPTIONS[1],
    [shiftFocusKey],
  );

  const activeBusiness = useMemo(
    () => {
      const businesses = loop.businesses?.businesses || [];
      return businesses.find((item) => item.is_active) || null;
    },
    [loop.businesses?.businesses],
  );
  const starterOptions = useMemo(
    () => loop.businesses?.starter_options || [
      { business_type: 'fruit_shop', label: 'Fruit Shop', cost_xgp: 500 },
      { business_type: 'food_truck', label: 'Food Truck', cost_xgp: 1200 },
    ],
    [loop.businesses?.starter_options],
  );
  const businessMarketListings = useMemo(
    () => deriveBusinessMarketListings({
      tiles: sandboxMap.tiles,
      starterOptions,
      activeBusiness,
    }),
    [activeBusiness, sandboxMap.tiles, starterOptions],
  );
  const selectedListing = useMemo(
    () => businessMarketListings.find((listing) => listing.listing_id === selectedListingId) || null,
    [businessMarketListings, selectedListingId],
  );
  const activeBusinessProfile = useMemo(
    () => deriveActiveBusinessProfile({
      activeBusiness,
      sandboxState: sandboxBusinessState,
      latestProfitXgp: Number(loop.businesses?.profit_snapshot.latest_daily_profit_xgp || 0),
      trailingProfitXgp: Number(loop.businesses?.profit_snapshot.trailing_7d_profit_xgp || 0),
      dayNumber,
    }),
    [activeBusiness, dayNumber, loop.businesses?.profit_snapshot.latest_daily_profit_xgp, loop.businesses?.profit_snapshot.trailing_7d_profit_xgp, sandboxBusinessState],
  );
  const ownedTileKeys = useMemo(
    () => sandboxBusinessState.owned_lots.map((lot) => lot.tile_key),
    [sandboxBusinessState.owned_lots],
  );
  const developedTileKeys = useMemo(
    () => sandboxBusinessState.owned_lots
      .filter((lot) => lot.development_stage === 'built')
      .map((lot) => lot.tile_key),
    [sandboxBusinessState.owned_lots],
  );
  const selectedLotOwnership = useMemo(
    () => sandboxBusinessState.owned_lots.find((lot) => lot.tile_key === selectedTile?.key) || null,
    [sandboxBusinessState.owned_lots, selectedTile?.key],
  );
  const selectedTileMode = useMemo(
    () => selectedTileModeLabel(selectedTile, selectedLotOwnership),
    [selectedLotOwnership, selectedTile],
  );
  const selectedTileStatus = useMemo(
    () => selectedTileStatusLabel(selectedTile, selectedLotOwnership),
    [selectedLotOwnership, selectedTile],
  );
  const selectedNodeTypeLabel = useMemo(
    () => formatMapNodeType(selectedTile?.nodeType),
    [selectedTile?.nodeType],
  );
  const operatedToday = loop.dailySession.actionsTakenToday.some(
    (entry) => canonicalMapActionKey(String(entry.action_key || '')) === 'operate_business' && entry.success,
  );

  const persistSandboxState = async (
    updater: (current: BusinessSandboxState) => BusinessSandboxState,
  ) => {
    const next = await updateBusinessSandboxState(loop.playerId, updater);
    setSandboxBusinessState(next);
    return next;
  };

  const closeSelectedTile = useCallback(() => {
    setSelectedTileKey(null);
  }, []);

  useFocusEffect(useCallback(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (!selectedTileKey) return false;
      setSelectedTileKey(null);
      return true;
    });
    return () => subscription.remove();
  }, [selectedTileKey]));

  useEffect(() => {
    const businessNodeActive = Boolean(selectedTile?.actionTags.includes('business_open') || selectedTile?.actionTags.includes('business_operate'));
    if (!businessNodeActive || businessMarketListings.length === 0) return;
    if (selectedListingId && businessMarketListings.some((listing) => listing.listing_id === selectedListingId)) return;
    setSelectedListingId(businessMarketListings[0]?.listing_id || null);
  }, [businessMarketListings, selectedListingId, selectedTile?.actionTags]);

  const travelGuard = useMemo(() => {
    if (!selectedTile?.travelOption) {
      return { allowed: false, reason: 'Select a travel-linked tile to move your location.', timeCostUnits: 0 };
    }
    return loop.dailySession.canExecuteAction(
      {
        action_key: 'travel',
        title: `Travel to ${selectedTile.travelOption.destination_label}`,
        description: 'Travel across the city map.',
        status: 'available',
        blockers: [],
      },
      Number(selectedTile.travelOption.time_cost_units || 0),
    );
  }, [loop.dailySession, selectedTile]);

  const handleTileSelect = (tile: SandboxMapTile) => {
    setSelectedTileKey(tile.key);
  };

  const handleTravel = async () => {
    if (!selectedTile?.travelOption || !travelGuard.allowed || loop.executingAction) return;
    await loop.executeAction({
      action_key: 'travel',
      title: `Travel to ${selectedTile.travelOption.destination_label}`,
      description: `Travel from ${selectedTile.travelOption.from_label} to ${selectedTile.travelOption.destination_label}.`,
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'high',
      parameters: {
        destination_key: selectedTile.travelOption.destination_key,
        time_cost_units: Number(selectedTile.travelOption.time_cost_units || 0),
      },
    });
  };

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
      description: 'Switch main job from the map Job Center.',
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
      description: 'Begin certification training from the map Job Center.',
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

  const openStarterBusinessFromMap = async (
    businessType: string,
    listing?: BusinessMarketListing | null,
  ) => {
    if (openingBusinessType || !selectedTile) return;
    setOpeningBusinessType(businessType);
    try {
      const result = await openBusiness(businessType, loop.playerId);
      if (listing) {
        await persistSandboxState((current) => ({
          ...current,
          business_market_links: [
            ...current.business_market_links.filter((item) => item.business_id !== result.business_id),
            {
              business_id: result.business_id,
              listing_id: listing.listing_id,
              listing_name: listing.listing_name,
              tile_key: listing.tile_key,
              district_key: listing.district_key,
              district_label: listing.district_label,
              location_label: listing.location_label,
              growth_phase_key: listing.growth_phase_key,
            },
          ],
        }));
      }
      loop.setFeedback({
        tone: 'success',
        message: `${listing?.listing_name || result.display_name} opened successfully. ${formatMoney(result.startup_cost)} invested.`,
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

  const toggleCompareListing = (listingId: string) => {
    setComparedListingIds((current) => {
      if (current.includes(listingId)) {
        return current.filter((item) => item !== listingId);
      }
      return [...current, listingId].slice(-2);
    });
  };

  const purchaseSelectedLot = async () => {
    if (!selectedTile?.landProfile || selectedLotOwnership) return;
    const landProfile = selectedTile.landProfile;
    await persistSandboxState((current) => ({
      ...current,
      owned_lots: [
        ...current.owned_lots,
        {
          tile_key: selectedTile.key,
          x: selectedTile.x,
          y: selectedTile.y,
          district_key: selectedTile.districtKey || null,
          district_label: selectedTile.districtLabel || null,
          zone_type: landProfile.zoneType,
          size: landProfile.size,
          value_xgp: landProfile.valueXgp,
          purchase_price_xgp: landProfile.valueXgp,
          traffic_score: landProfile.trafficScore,
          development_potential: landProfile.developmentPotential,
          planned_business_type: null,
          placed_business_id: null,
          development_stage: 'land',
          purchased_at: new Date().toISOString(),
        },
      ],
    }));
    loop.setFeedback({
      tone: 'success',
      message: `${selectedTile.label} secured as a development lot.`,
    });
  };

  const placeActiveBusinessOnLot = async () => {
    if (!selectedTile || !selectedLotOwnership || !activeBusiness) return;
    await persistSandboxState((current) => ({
      ...current,
      owned_lots: current.owned_lots.map((lot) => (
        lot.tile_key !== selectedTile.key
          ? lot
          : {
            ...lot,
            planned_business_type: String(activeBusiness.business_type),
            placed_business_id: activeBusiness.business_id,
            development_stage: 'built',
          }
      )),
      business_market_links: current.business_market_links.map((link) => (
        link.business_id !== activeBusiness.business_id
          ? link
          : {
            ...link,
            tile_key: selectedTile.key,
            district_key: selectedTile.districtKey || null,
            district_label: selectedTile.districtLabel || null,
            location_label: `${selectedTile.districtLabel || 'Owned lot'} (${selectedTile.x},${selectedTile.y})`,
          }
      )),
    }));
    loop.setFeedback({
      tone: 'success',
      message: `${activeBusiness.business_name || businessLabel(activeBusiness.business_type)} placed on this lot.`,
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
          listing_id: marketLinkIdForBusiness(current, activeBusinessProfile.business_id, selectedListing?.listing_id || ''),
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

  const tileRequiresPresence = (tag: MapTileActionTag): boolean => (
    tag !== 'business_open'
  );

  const locationLockedReason = selectedTile && !selectedTile.isCurrentLocation
    ? `Travel to ${selectedTile.label} before using this node.`
    : null;
  const jobBoardActive = Boolean(selectedTile?.actionTags.includes('job_board'));
  const workNodeActive = Boolean(selectedTile?.actionTags.includes('work_shift'));
  const businessNodeActive = Boolean(
    selectedTile?.actionTags.includes('business_open')
    || selectedTile?.actionTags.includes('business_operate')
    || selectedTile?.actionTags.includes('business_inventory'),
  );
  const jobBoardDisabledReason = jobBoardActive && !selectedTile?.isCurrentLocation
    ? `Travel to ${selectedTile?.label || 'the Job Center'} before applying or starting certifications.`
    : null;
  const businessNodeDisabledReason = businessNodeActive && !selectedTile?.isCurrentLocation
    ? `Travel to ${selectedTile?.label || 'the Business District'} before buying or operating a business.`
    : null;

  const tileActionButtons: TileActionButton[] = (() => {
    if (!selectedTile) return [];

    const buttons: TileActionButton[] = [];
    const actionTags = selectedTile.actionTags || [];

    actionTags.forEach((tag) => {
      const requiresPresence = tileRequiresPresence(tag);
      const locationLocked = Boolean(requiresPresence && !selectedTile.isCurrentLocation);

      if (tag === 'meal_breakfast') {
        buttons.push({
          key: 'meal_breakfast',
          label: 'Buy Breakfast',
          detail: 'Grocery lane food action routed through the meal system.',
          variant: 'primary',
          disabled: locationLocked || loop.executingAction || cash < 6,
          onPress: () => { void executeMealFromMap('breakfast'); },
        });
        return;
      }

      if (tag === 'meal_lunch') {
        buttons.push({
          key: 'meal_lunch',
          label: 'Buy Lunch',
          detail: 'Fast grocery stop for the midday food lane.',
          variant: 'secondary',
          disabled: locationLocked || loop.executingAction || cash < 6,
          onPress: () => { void executeMealFromMap('lunch'); },
        });
        return;
      }

      if (tag === 'meal_dinner') {
        buttons.push({
          key: 'meal_dinner',
          label: 'Eat Dinner',
          detail: 'Restaurant and food truck dinner action.',
          variant: 'primary',
          disabled: locationLocked || loop.executingAction || daySettled || dinnerResolvedToday,
          onPress: () => { void executeMealFromMap('dinner'); },
        });
        return;
      }

      if (tag === 'work_shift') {
        buttons.push({
          key: 'work_shift',
          label: workShiftAction?.title || 'Start Shift',
          detail: `${selectedShiftFocus.label} selected. ${selectedShiftFocus.bonusXp} bonus XP if you run this shift from the map.`,
          variant: 'primary',
          disabled: locationLocked || loop.executingAction || !workShiftAction || loop.dailySession.canExecuteAction(workShiftAction).allowed === false,
          onPress: () => {
            void executeMapAction(
              workShiftAction,
              'No work shift is available right now.',
              { shift_focus: selectedShiftFocus.key },
            );
          },
        });
        return;
      }

      if (tag === 'rideshare') {
        buttons.push({
          key: 'rideshare',
          label: 'Run 1 Trip',
          detail: 'Start rideshare from a hotspot tile instead of the dashboard lane.',
          variant: 'primary',
          disabled: locationLocked || loop.executingAction || !sideIncomeAction || loop.dailySession.canExecuteAction(sideIncomeAction).allowed === false,
          onPress: () => { void executeMapAction(sideIncomeAction, 'Rideshare is not available at this location right now.'); },
        });
        return;
      }

      if (tag === 'recovery') {
        buttons.push({
          key: 'recovery',
          label: leisureActivityRunning ? 'Stop Leisure' : 'Relax Here',
          detail: leisureActivityRunning
            ? 'Stop the current leisure session.'
            : 'Start a timed leisure recovery session from the map.',
          variant: 'secondary',
          disabled: locationLocked || loop.executingAction,
          onPress: toggleRecoveryFromMap,
        });
        return;
      }

      if (tag === 'business_operate' && activeBusiness) {
        buttons.push({
          key: 'business_operate',
          label: operatedToday ? 'Operated Today' : 'Run Business',
          detail: 'Operate the active business from its district node.',
          variant: 'primary',
          disabled: locationLocked || loop.executingAction || operatedToday || loop.dailySession.sessionStatus !== 'active',
          onPress: () => { void loop.operateBusiness(); },
        });
        return;
      }

      if (tag === 'business_inventory' && activeBusiness && inventoryAction) {
        buttons.push({
          key: 'business_inventory',
          label: 'Restock Inventory',
          detail: 'Buy inventory from the map instead of a generic business button.',
          variant: 'secondary',
          disabled: locationLocked || loop.executingAction || loop.dailySession.canExecuteAction(inventoryAction).allowed === false,
          onPress: () => { void executeMapAction(inventoryAction, 'Inventory restock is unavailable right now.'); },
        });
        return;
      }

      if (tag === 'business_open' && !activeBusiness) {
        if (selectedListing) {
          const need = Math.max(selectedListing.price_xgp - cash, 0);
          buttons.push({
            key: `business_open_${selectedListing.listing_id}`,
            label: need > 0
              ? `${selectedListing.listing_name} (${formatMoney(need)} short)`
              : `Buy ${selectedListing.listing_name}`,
            detail: `${selectedListing.growth_phase_label} · ${selectedListing.location_label}.`,
            variant: 'primary',
            disabled: locationLocked || Boolean(openingBusinessType) || need > 0 || !selectedListing.buyable,
            onPress: () => { void openStarterBusinessFromMap(String(selectedListing.business_type), selectedListing); },
          });
        } else {
          starterOptions.forEach((option, index) => {
            const need = Math.max(option.cost_xgp - cash, 0);
            buttons.push({
              key: `business_open_${option.business_type}`,
              label: need > 0 ? `${option.label} (${formatMoney(need)} short)` : `Open ${option.label}`,
              detail: `Startup cost ${formatMoney(option.cost_xgp)}.`,
              variant: index === 0 ? 'primary' : 'secondary',
              disabled: locationLocked || Boolean(openingBusinessType) || need > 0,
              onPress: () => { void openStarterBusinessFromMap(option.business_type); },
            });
          });
        }
      }
    });

    return buttons;
  })();

  const bottomTabs = useMemo(() => ([
    { key: 'map' as OnboardingRouteKey, label: 'Map', icon: '\u{1F5FA}\u{FE0F}' },
    { key: 'work' as OnboardingRouteKey, label: 'Work', icon: '\u{1F4BC}' },
    { key: 'business' as OnboardingRouteKey, label: 'Business', icon: '\u{1F3EA}' },
    { key: 'dashboard' as OnboardingRouteKey, label: 'Wallet', icon: '\u{1F4B0}' },
    { key: 'life' as OnboardingRouteKey, label: 'Life', icon: '\u{2764}\u{FE0F}' },
  ]), []);

  return (
    <SafeAreaPage edges={['top', 'bottom']}>
      <View style={styles.root}>
        <PlayerStatusBar
          cash={cash}
          stress={stress}
          health={health}
          dayNumber={dayNumber}
        />

        <View style={styles.headerStrip}>
          <View style={styles.headerCard}>
            <Text style={styles.headerEyebrow}>Houston Sandbox</Text>
            <Text style={styles.headerTitle}>Map-first economy layer</Text>
            <Text style={styles.headerBody}>
              Core work, food, rideshare, leisure, and business actions now live on the map itself.
            </Text>
          </View>
          <View style={styles.metricRail}>
            <View style={styles.metricChip}>
              <Text style={styles.metricLabel}>Current</Text>
              <Text style={styles.metricValue}>{currentLocationLabel}</Text>
            </View>
            <View style={styles.metricChip}>
              <Text style={styles.metricLabel}>Selected</Text>
              <Text style={styles.metricValue}>
                {selectedTile ? `${selectedTile.x},${selectedTile.y}` : '--'}
              </Text>
            </View>
            <View style={styles.metricChip}>
              <Text style={styles.metricLabel}>Zoom</Text>
              <Text style={styles.metricValue}>{Math.round(zoomLevel * 100)}%</Text>
            </View>
          </View>
        </View>

        <View style={styles.mapStage}>
          <View style={styles.mapArea}>
            <GameMap
              map={sandboxMap}
              selectedTileKey={selectedTileKey}
              onTileSelect={handleTileSelect}
              onZoomChange={setZoomLevel}
              ownedTileKeys={ownedTileKeys}
              developedTileKeys={developedTileKeys}
            />

            <View pointerEvents="none" style={styles.mapInfoDock}>
              <View style={styles.mapHeroCard}>
                <Text style={styles.mapHeroEyebrow}>Houston Sandbox</Text>
                <Text style={styles.mapHeroTitle}>{currentLocationLabel}</Text>
                <Text style={styles.mapHeroBody}>
                  {detailSheetOpen
                    ? 'Slot detail is open. Close it to return to full map browsing.'
                    : 'Tap any slot to inspect land, service buildings, work nodes, meals, or business frontage.'}
                </Text>
              </View>
              <View style={styles.mapMetricRail}>
                <View style={styles.mapMetricChip}>
                  <Text style={styles.mapMetricLabel}>Current</Text>
                  <Text style={styles.mapMetricValue}>{currentLocationLabel}</Text>
                </View>
                <View style={styles.mapMetricChip}>
                  <Text style={styles.mapMetricLabel}>Selected</Text>
                  <Text style={styles.mapMetricValue}>
                    {selectedTile ? `${selectedTile.x},${selectedTile.y}` : 'Browse'}
                  </Text>
                </View>
                <View style={styles.mapMetricChip}>
                  <Text style={styles.mapMetricLabel}>Zoom</Text>
                  <Text style={styles.mapMetricValue}>{Math.round(zoomLevel * 100)}%</Text>
                </View>
              </View>
            </View>

            {!detailSheetOpen ? (
              <View pointerEvents="none" style={styles.mapBrowseHint}>
                <Text style={styles.mapBrowseHintTitle}>Browse Mode</Text>
                <Text style={styles.mapBrowseHintBody}>
                  Pan the city, zoom for frontage detail, then tap a slot to open its detail sheet.
                </Text>
              </View>
            ) : null}

            <MapDetailSheet
              visible={detailSheetOpen}
              title={selectedTile?.label || 'Selected Slot'}
              subtitle={selectedTile ? `${selectedDistrict?.label || selectedTile.districtLabel || 'Outer ring'} / ${selectedTile.x},${selectedTile.y}` : null}
              onClose={closeSelectedTile}
            >
              <View style={styles.selectionPanel}>
                <View style={styles.sheetTopActions}>
                  <SecondaryButton label="Back to Map" onPress={closeSelectedTile} />
                </View>

                <View style={styles.selectionHeader}>
                  <View style={styles.selectionTitleWrap}>
                    <Text style={styles.selectionEyebrow}>Selected Slot</Text>
                    <Text style={styles.selectionTitle}>
                      {selectedTile?.label || 'Pick a tile'}
                    </Text>
                  </View>
                  <View style={styles.kindBadge}>
                    <Text style={styles.kindBadgeText}>
                      {selectedTileMode}
                    </Text>
                  </View>
                </View>

                <View style={styles.selectionBadgeRow}>
                  {selectedNodeTypeLabel ? (
                    <View style={[styles.detailBadge, styles.detailBadgePrimary]}>
                      <Text style={styles.detailBadgeText}>{selectedNodeTypeLabel}</Text>
                    </View>
                  ) : null}
                  {selectedTile?.opportunityTier ? (
                    <View style={styles.detailBadge}>
                      <Text style={styles.detailBadgeText}>
                        {String(selectedTile.opportunityTier).toUpperCase()} tier
                      </Text>
                    </View>
                  ) : null}
                  <View style={styles.detailBadge}>
                    <Text style={styles.detailBadgeText}>{selectedTileStatus}</Text>
                  </View>
                </View>

                <View style={styles.selectionStatsRow}>
                  <View style={styles.selectionStat}>
                    <Text style={styles.selectionStatLabel}>Coords</Text>
                    <Text style={styles.selectionStatValue}>
                      {selectedTile ? `${selectedTile.x}, ${selectedTile.y}` : '--'}
                    </Text>
                  </View>
                  <View style={styles.selectionStat}>
                    <Text style={styles.selectionStatLabel}>District</Text>
                    <Text style={styles.selectionStatValue}>
                      {selectedDistrict?.label || selectedTile?.districtLabel || 'Outer ring'}
                    </Text>
                  </View>
                  <View style={styles.selectionStat}>
                    <Text style={styles.selectionStatLabel}>Status</Text>
                    <Text style={styles.selectionStatValue}>{selectedTileStatus}</Text>
                  </View>
                </View>

          <Text style={styles.selectionDescription}>
            {selectedTile?.description || 'Tap any tile to inspect land slots, roads, service buildings, businesses, and future expansion nodes.'}
          </Text>

          {selectedTile?.landProfile ? (
            <View style={styles.landMetricsBox}>
              <Text style={styles.actionSectionTitle}>Land Profile</Text>
              <View style={styles.landMetricsRow}>
                <View style={styles.landMetricCard}>
                  <Text style={styles.landMetricLabel}>Zone</Text>
                  <Text style={styles.landMetricValue}>{describeZoneType(selectedTile.landProfile.zoneType)}</Text>
                </View>
                <View style={styles.landMetricCard}>
                  <Text style={styles.landMetricLabel}>Size</Text>
                  <Text style={styles.landMetricValue}>{describeLotSize(selectedTile.landProfile.size)}</Text>
                </View>
                <View style={styles.landMetricCard}>
                  <Text style={styles.landMetricLabel}>Value</Text>
                  <Text style={styles.landMetricValue}>{formatMoney(selectedTile.landProfile.valueXgp)}</Text>
                </View>
                <View style={styles.landMetricCard}>
                  <Text style={styles.landMetricLabel}>Traffic</Text>
                  <Text style={styles.landMetricValue}>{selectedTile.landProfile.trafficScore}/100</Text>
                </View>
                <View style={styles.landMetricCard}>
                  <Text style={styles.landMetricLabel}>Dev</Text>
                  <Text style={styles.landMetricValue}>{selectedTile.landProfile.developmentPotential}/100</Text>
                </View>
              </View>
            </View>
          ) : null}

          {selectedTile?.travelOption ? (
            <View style={styles.travelRow}>
              <View style={styles.travelMeta}>
                <Text style={styles.travelMetaLine}>
                  Travel: {selectedTile.travelOption.time_cost_units}u
                  {' · '}
                  {formatMoney(selectedTile.travelOption.cash_cost_xgp)}
                </Text>
                <Text style={styles.travelMetaLine}>
                  Stress {selectedTile.travelOption.stress_delta >= 0 ? '+' : ''}{selectedTile.travelOption.stress_delta}
                  {' · '}
                  {selectedTile.travelOption.destination_region}
                </Text>
              </View>
              <PrimaryButton
                label={`Travel ${selectedTile.travelOption.time_cost_units}u`}
                onPress={() => { void handleTravel(); }}
                disabled={!travelGuard.allowed || loop.executingAction || selectedTile.isCurrentLocation}
              />
            </View>
          ) : null}

          {tileActionButtons.length > 0 ? (
            <View style={styles.actionSection}>
              <Text style={styles.actionSectionTitle}>Actions At This Node</Text>
              {locationLockedReason ? (
                <Text style={styles.guardText}>{locationLockedReason}</Text>
              ) : null}
              {tileActionButtons.map((button) => (
                <View key={button.key} style={styles.actionRow}>
                  <View style={styles.actionCopy}>
                    <Text style={styles.actionTitle}>{button.label}</Text>
                    <Text style={styles.actionDetail}>{button.detail}</Text>
                  </View>
                  <View style={styles.actionButtonWrap}>
                    {button.variant === 'primary' ? (
                      <PrimaryButton
                        label={button.label}
                        onPress={button.onPress}
                        disabled={button.disabled}
                      />
                    ) : (
                      <SecondaryButton
                        label={button.label}
                        onPress={button.onPress}
                        disabled={button.disabled}
                      />
                    )}
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <View style={styles.actionSection}>
              <Text style={styles.actionSectionTitle}>Map Interaction</Text>
              <Text style={styles.actionDetail}>
                This slot is terrain, infrastructure, or a future development surface. Core life actions appear on grocery, Job Center, work, rideshare, leisure, dinner, and business nodes.
              </Text>
            </View>
          )}

          {businessNodeActive ? (
            <BusinessMarketPanel
              listings={businessMarketListings}
              selectedListingId={selectedListingId}
              comparedListingIds={comparedListingIds}
              activeBusinessProfile={activeBusinessProfile}
              canTransact={!businessNodeDisabledReason}
              onInspectListing={setSelectedListingId}
              onToggleCompare={toggleCompareListing}
              onBuyListing={(listing) => { void openStarterBusinessFromMap(String(listing.business_type), listing); }}
              onAdvancePhase={() => { void advanceActiveBusinessPhase(); }}
            />
          ) : null}

          {selectedTile?.landProfile ? (
            <View style={styles.landControlBox}>
              <Text style={styles.actionSectionTitle}>Land Development</Text>
              <Text style={styles.actionDetail}>
                Buy empty lots, hold them for traffic growth, and place your active business onto precise map slots.
              </Text>
              {selectedLotOwnership ? (
                <>
                  <Text style={styles.landOwnedText}>
                    Owned lot · {selectedLotOwnership.development_stage === 'built' ? 'Business placed' : 'Ready for development'}
                  </Text>
                  <Text style={styles.actionDetail}>
                    {selectedLotOwnership.placed_business_id
                      ? `Linked business: ${activeBusinessProfile?.display_name || businessLabel(activeBusiness?.business_type || '')}`
                      : 'No business placed yet.'}
                  </Text>
                  <PrimaryButton
                    label={selectedLotOwnership.placed_business_id ? 'Business Placed' : activeBusiness ? `Place ${activeBusinessProfile?.growth_phase_label || businessLabel(activeBusiness.business_type)} Here` : 'Need Active Business'}
                    onPress={selectedLotOwnership.placed_business_id || !activeBusiness ? undefined : () => { void placeActiveBusinessOnLot(); }}
                    disabled={Boolean(selectedLotOwnership.placed_business_id) || !activeBusiness}
                  />
                </>
              ) : (
                <>
                  <Text style={styles.actionDetail}>
                    Purchase price {formatMoney(selectedTile.landProfile.valueXgp)} · Traffic {selectedTile.landProfile.trafficScore}/100 · Development {selectedTile.landProfile.developmentPotential}/100
                  </Text>
                  <PrimaryButton
                    label={`Purchase Lot ${formatMoney(selectedTile.landProfile.valueXgp)}`}
                    onPress={() => { void purchaseSelectedLot(); }}
                    disabled={false}
                  />
                </>
              )}
            </View>
          ) : null}

          {workNodeActive && workShiftAction ? (
            <View style={styles.shiftTaskPanel}>
              <Text style={styles.actionSectionTitle}>Shift Focus</Text>
              <Text style={styles.actionDetail}>
                Light first version: pick one fast focus before clocking in to gain bonus job XP and speed up promotions.
              </Text>
              <View style={styles.shiftFocusList}>
                {SHIFT_FOCUS_OPTIONS.map((option) => {
                  const selected = option.key === selectedShiftFocus.key;
                  return (
                    <Pressable
                      key={option.key}
                      onPress={() => setShiftFocusKey(option.key)}
                      style={({ pressed }) => [
                        styles.shiftFocusCard,
                        selected ? styles.shiftFocusCardActive : null,
                        pressed ? styles.shiftFocusCardPressed : null,
                      ]}
                    >
                      <Text style={[styles.shiftFocusTitle, selected ? styles.shiftFocusTitleActive : null]}>
                        {option.label}
                      </Text>
                      <Text style={styles.shiftFocusDetail}>{option.detail}</Text>
                      <Text style={styles.shiftFocusBonus}>Bonus: +{option.bonusXp} XP</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          ) : null}

          {jobBoardActive ? (
            <JobMarketPanel
              jobMarket={workState?.job_market || null}
              executingAction={loop.executingAction}
              busyActionKey={loop.busyActionKey}
              onSwitchJob={switchToMarketJob}
              onStartTraining={startMarketTraining}
              interactionDisabledReason={jobBoardDisabledReason}
            />
          ) : null}

          {selectedTile?.actionTags.includes('meal_breakfast') || selectedTile?.actionTags.includes('meal_lunch') ? (
            <Text style={styles.hintText}>
              Grocery is temporarily routed through meal actions until a dedicated grocery purchasing action exists.
            </Text>
          ) : null}

          {businessNodeDisabledReason ? (
            <Text style={styles.guardText}>{businessNodeDisabledReason}</Text>
          ) : null}

          {!travelGuard.allowed && selectedTile?.travelOption && !selectedTile.isCurrentLocation ? (
            <Text style={styles.guardText}>{travelGuard.reason}</Text>
          ) : null}
              </View>
            </MapDetailSheet>
          </View>
        </View>

        <View style={styles.bottomNav}>
          {bottomTabs.map((tab) => {
            const active = tab.key === 'map';
            return (
              <Pressable
                key={tab.key}
                onPress={() => {
                  if (active) return;
                  onboarding.navigateTo(tab.key);
                }}
                style={({ pressed }) => [
                  styles.tab,
                  active ? styles.tabActive : null,
                  pressed ? styles.tabPressed : null,
                ]}
              >
                <Text style={[styles.tabIcon, active ? styles.tabIconActive : null]}>{tab.icon}</Text>
                <Text style={[styles.tabLabel, active ? styles.tabLabelActive : null]}>{tab.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    </SafeAreaPage>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  headerStrip: {
    paddingHorizontal: 12,
    paddingTop: 6,
    paddingBottom: 4,
    gap: 8,
  },
  headerCard: {
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: '#0b1220',
    borderWidth: 1,
    borderColor: '#172033',
  },
  headerEyebrow: {
    ...theme.typography.caption,
    color: '#67e8f9',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  headerTitle: {
    marginTop: 2,
    ...theme.typography.bodyMd,
    color: '#f8fafc',
    fontWeight: '800',
  },
  headerBody: {
    marginTop: 2,
    ...theme.typography.caption,
    color: '#94a3b8',
  },
  metricRail: {
    flexDirection: 'row',
    gap: 8,
  },
  metricChip: {
    flex: 1,
    borderRadius: 14,
    paddingHorizontal: 10,
    paddingVertical: 8,
    backgroundColor: '#0b1220',
    borderWidth: 1,
    borderColor: '#172033',
  },
  metricLabel: {
    ...theme.typography.caption,
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  metricValue: {
    marginTop: 3,
    ...theme.typography.bodySm,
    color: '#f8fafc',
    fontWeight: '700',
  },
  mapStage: {
    flex: 1,
  },
  mapArea: {
    flex: 1,
    marginHorizontal: 12,
    marginTop: 8,
    marginBottom: 10,
    position: 'relative',
    overflow: 'hidden',
  },
  mapInfoDock: {
    position: 'absolute',
    left: 14,
    right: 84,
    top: 86,
    gap: 10,
  },
  mapHeroCard: {
    alignSelf: 'flex-start',
    maxWidth: 280,
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 12,
    backgroundColor: 'rgba(7, 13, 26, 0.86)',
    borderWidth: 1,
    borderColor: 'rgba(103, 232, 249, 0.14)',
  },
  mapHeroEyebrow: {
    ...theme.typography.caption,
    color: '#67e8f9',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  mapHeroTitle: {
    marginTop: 3,
    ...theme.typography.headingSm,
    color: '#f8fafc',
  },
  mapHeroBody: {
    marginTop: 4,
    ...theme.typography.bodySm,
    color: '#cbd5e1',
  },
  mapMetricRail: {
    flexDirection: 'row',
    gap: 8,
  },
  mapMetricChip: {
    flex: 1,
    borderRadius: 16,
    paddingHorizontal: 10,
    paddingVertical: 9,
    backgroundColor: 'rgba(7, 13, 26, 0.82)',
    borderWidth: 1,
    borderColor: 'rgba(148, 163, 184, 0.14)',
  },
  mapMetricLabel: {
    ...theme.typography.caption,
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  mapMetricValue: {
    marginTop: 3,
    ...theme.typography.bodySm,
    color: '#f8fafc',
    fontWeight: '700',
  },
  mapBrowseHint: {
    position: 'absolute',
    left: 14,
    right: 14,
    bottom: 14,
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 12,
    backgroundColor: 'rgba(7, 13, 26, 0.9)',
    borderWidth: 1,
    borderColor: 'rgba(148, 163, 184, 0.14)',
  },
  mapBrowseHintTitle: {
    ...theme.typography.caption,
    color: '#67e8f9',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  mapBrowseHintBody: {
    marginTop: 4,
    ...theme.typography.bodySm,
    color: '#cbd5e1',
  },
  selectionPanel: {
    gap: 12,
  },
  sheetTopActions: {
    alignItems: 'flex-start',
  },
  selectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 10,
  },
  selectionTitleWrap: {
    flex: 1,
  },
  selectionEyebrow: {
    ...theme.typography.caption,
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  selectionTitle: {
    marginTop: 3,
    ...theme.typography.headingSm,
    color: '#f8fafc',
  },
  kindBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#334155',
  },
  kindBadgeText: {
    ...theme.typography.caption,
    color: '#cbd5e1',
  },
  selectionBadgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  detailBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: 'rgba(15, 23, 42, 0.92)',
    borderWidth: 1,
    borderColor: 'rgba(148, 163, 184, 0.16)',
  },
  detailBadgePrimary: {
    borderColor: 'rgba(103, 232, 249, 0.28)',
    backgroundColor: 'rgba(8, 47, 73, 0.36)',
  },
  detailBadgeText: {
    ...theme.typography.caption,
    color: '#dbeafe',
    fontWeight: '700',
  },
  selectionStatsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  selectionStat: {
    flex: 1,
    borderRadius: 16,
    paddingHorizontal: 10,
    paddingVertical: 9,
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#1f2937',
  },
  selectionStatLabel: {
    ...theme.typography.caption,
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  selectionStatValue: {
    marginTop: 3,
    ...theme.typography.bodySm,
    color: '#f8fafc',
    fontWeight: '700',
  },
  selectionDescription: {
    ...theme.typography.bodySm,
    color: '#cbd5e1',
  },
  landMetricsBox: {
    gap: 8,
  },
  landMetricsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  landMetricCard: {
    flex: 1,
    minWidth: 92,
    borderRadius: 14,
    paddingHorizontal: 10,
    paddingVertical: 10,
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#1f2937',
    gap: 4,
  },
  landMetricLabel: {
    ...theme.typography.caption,
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  landMetricValue: {
    ...theme.typography.bodySm,
    color: '#f8fafc',
    fontWeight: '700',
  },
  travelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  travelMeta: {
    flex: 1,
    gap: 4,
  },
  travelMetaLine: {
    ...theme.typography.bodySm,
    color: '#e2e8f0',
  },
  actionSection: {
    gap: 10,
  },
  actionSectionTitle: {
    ...theme.typography.caption,
    color: '#67e8f9',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  actionRow: {
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#1f2937',
    gap: 10,
  },
  actionCopy: {
    gap: 4,
  },
  actionTitle: {
    ...theme.typography.bodyMd,
    color: '#f8fafc',
    fontWeight: '700',
  },
  actionDetail: {
    ...theme.typography.bodySm,
    color: '#cbd5e1',
  },
  actionButtonWrap: {
    width: '100%',
  },
  landControlBox: {
    gap: 10,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#1f2937',
  },
  landOwnedText: {
    ...theme.typography.bodySm,
    color: '#4ade80',
    fontWeight: '700',
  },
  shiftTaskPanel: {
    gap: 10,
  },
  shiftFocusList: {
    gap: 8,
  },
  shiftFocusCard: {
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: '#0f172a',
    borderWidth: 1,
    borderColor: '#1f2937',
    gap: 4,
  },
  shiftFocusCardActive: {
    borderColor: '#38bdf8',
    backgroundColor: 'rgba(14, 165, 233, 0.12)',
  },
  shiftFocusCardPressed: {
    opacity: 0.8,
  },
  shiftFocusTitle: {
    ...theme.typography.bodyMd,
    color: '#f8fafc',
    fontWeight: '700',
  },
  shiftFocusTitleActive: {
    color: '#67e8f9',
  },
  shiftFocusDetail: {
    ...theme.typography.bodySm,
    color: '#cbd5e1',
  },
  shiftFocusBonus: {
    ...theme.typography.caption,
    color: '#67e8f9',
    fontWeight: '700',
  },
  hintText: {
    ...theme.typography.caption,
    color: '#cbd5e1',
  },
  guardText: {
    ...theme.typography.caption,
    color: '#fbbf24',
  },
  bottomNav: {
    flexDirection: 'row',
    backgroundColor: '#111827',
    borderTopWidth: 1,
    borderTopColor: '#1f2937',
    paddingHorizontal: 6,
    paddingTop: 6,
    paddingBottom: 8,
    gap: 4,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    paddingHorizontal: 2,
    borderRadius: 10,
    gap: 2,
  },
  tabActive: {
    backgroundColor: 'rgba(59, 130, 246, 0.18)',
  },
  tabPressed: {
    opacity: 0.7,
  },
  tabIcon: {
    fontSize: 20,
    opacity: 0.7,
  },
  tabIconActive: {
    opacity: 1,
  },
  tabLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#94a3b8',
  },
  tabLabelActive: {
    color: '#60a5fa',
  },
});

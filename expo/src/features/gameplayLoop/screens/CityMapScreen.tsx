import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, LayoutChangeEvent, Pressable, StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { formatMoney } from '@/lib/gameplayFormatters';

import { useGameplayLoop } from '../context';
import {
  GameplayCompactMetricRows,
  GameplayStickyActionArea,
  GameplaySummaryCard,
  GameplayWarningBanner,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

type OpportunityTier = 'high' | 'moderate' | 'low' | string;

const PIN_LAYOUT: Record<string, { x: number; y: number }> = {
  home: { x: 14, y: 74 },
  grocery: { x: 22, y: 28 },
  rideshare_hotspot_suburban: { x: 33, y: 52 },
  work: { x: 72, y: 67 },
  rideshare_hotspot_downtown: { x: 76, y: 30 },
  business_spot: { x: 58, y: 52 },
};

const FALLBACK_NODES = [
  { key: 'home', label: 'Home', region: 'Suburban', node_type: 'home', opportunity_tier: 'moderate', rideshare_quality: 'low', is_current_location: true },
  { key: 'work', label: 'Work', region: 'Downtown', node_type: 'work', opportunity_tier: 'moderate', rideshare_quality: 'moderate', is_current_location: false },
  { key: 'grocery', label: 'Grocery / Food', region: 'Suburban', node_type: 'grocery', opportunity_tier: 'low', rideshare_quality: 'restricted', is_current_location: false },
  { key: 'rideshare_hotspot_downtown', label: 'Downtown Rideshare Hotspot', region: 'Downtown', node_type: 'rideshare_hotspot', opportunity_tier: 'high', rideshare_quality: 'high', is_current_location: false },
  { key: 'rideshare_hotspot_suburban', label: 'Suburban Rideshare Hotspot', region: 'Suburban', node_type: 'rideshare_hotspot', opportunity_tier: 'moderate', rideshare_quality: 'moderate', is_current_location: false },
  { key: 'business_spot', label: 'Business Spot (Soon)', region: 'Downtown', node_type: 'business', opportunity_tier: 'moderate', rideshare_quality: 'restricted', is_current_location: false },
];

function toneForOpportunity(tier: OpportunityTier): 'positive' | 'warning' | 'danger' | 'info' | 'neutral' {
  const normalized = String(tier || '').toLowerCase();
  if (normalized === 'high') return 'positive';
  if (normalized === 'low') return 'warning';
  return 'info';
}

function colorForOpportunity(tier: OpportunityTier): string {
  const normalized = String(tier || '').toLowerCase();
  if (normalized === 'high') return theme.ui.positive;
  if (normalized === 'low') return theme.ui.warning;
  return theme.ui.action;
}

function actionsForNode(nodeType: string): string {
  const normalized = String(nodeType || '').toLowerCase();
  if (normalized === 'rideshare_hotspot') return 'Ride share (best), Travel';
  if (normalized === 'work') return 'Work shift, Ride share, Travel';
  if (normalized === 'grocery') return 'Meals, Travel';
  if (normalized === 'business') return 'Business lane (soon), Travel';
  return 'Meals, Recovery, Ride share, Travel';
}

export default function CityMapScreen() {
  useScreenTimer('map');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const workState = loop.dashboard?.work_state || loop.actionHub?.work_state || null;
  const cityMap = workState?.city_map || null;
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
  const currentLocationRegion = String(
    workState?.current_location_region
    || cityMap?.current_location_region
    || 'Suburban',
  );

  const nodes = useMemo(
    () => (cityMap?.nodes && cityMap.nodes.length > 0 ? cityMap.nodes : FALLBACK_NODES),
    [cityMap?.nodes],
  );
  const travelOptions = useMemo(
    () => (
      (workState?.travel_options && workState.travel_options.length > 0
        ? workState.travel_options
        : cityMap?.travel_options)
      || []
    ),
    [cityMap?.travel_options, workState?.travel_options],
  );

  const [selectedDestinationKey, setSelectedDestinationKey] = useState<string | null>(null);
  const [traveling, setTraveling] = useState(false);
  const [mapSize, setMapSize] = useState({ width: 0, height: 0 });

  const pulseAnim = useRef(new Animated.Value(1)).current;
  const arrivalAnim = useRef(new Animated.Value(1)).current;
  const routeAnim = useRef(new Animated.Value(0)).current;
  const detailsAnim = useRef(new Animated.Value(0)).current;
  const prevLocationKeyRef = useRef(currentLocationKey);

  useEffect(() => {
    const loopAnim = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.09, duration: 950, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1.0, duration: 950, useNativeDriver: true }),
      ]),
    );
    loopAnim.start();
    return () => loopAnim.stop();
  }, [pulseAnim]);

  useEffect(() => {
    if (prevLocationKeyRef.current === currentLocationKey) return;
    prevLocationKeyRef.current = currentLocationKey;
    arrivalAnim.setValue(1);
    Animated.sequence([
      Animated.timing(arrivalAnim, { toValue: 1.2, duration: 170, useNativeDriver: true }),
      Animated.timing(arrivalAnim, { toValue: 1.0, duration: 220, useNativeDriver: true }),
    ]).start();
  }, [arrivalAnim, currentLocationKey]);

  useEffect(() => {
    detailsAnim.setValue(0);
    if (!selectedDestinationKey) return;
    Animated.timing(detailsAnim, { toValue: 1, duration: 220, useNativeDriver: true }).start();
  }, [detailsAnim, selectedDestinationKey]);

  useEffect(() => {
    if (!selectedDestinationKey) return;
    if (selectedDestinationKey === currentLocationKey) {
      setSelectedDestinationKey(null);
    }
  }, [currentLocationKey, selectedDestinationKey]);

  const selectedTravelOption = useMemo(
    () => travelOptions.find((option) => String(option.destination_key) === selectedDestinationKey) || null,
    [selectedDestinationKey, travelOptions],
  );

  const executionGuard = useMemo(() => {
    if (!selectedTravelOption) {
      return { allowed: false, reason: 'Select a destination to travel.', timeCostUnits: 0 };
    }
    return loop.dailySession.canExecuteAction(
      {
        action_key: 'travel',
        title: `Travel to ${selectedTravelOption.destination_label}`,
        description: 'Travel across the city map.',
        status: 'available',
        blockers: [],
      },
      Number(selectedTravelOption.time_cost_units || 0),
    );
  }, [loop.dailySession, selectedTravelOption]);

  const routeGeometry = useMemo(() => {
    if (!selectedTravelOption || mapSize.width <= 0 || mapSize.height <= 0) return null;
    const fromLayout = PIN_LAYOUT[currentLocationKey];
    const toLayout = PIN_LAYOUT[selectedTravelOption.destination_key];
    if (!fromLayout || !toLayout) return null;
    const x1 = (fromLayout.x / 100) * mapSize.width;
    const y1 = (fromLayout.y / 100) * mapSize.height;
    const x2 = (toLayout.x / 100) * mapSize.width;
    const y2 = (toLayout.y / 100) * mapSize.height;
    const dx = x2 - x1;
    const dy = y2 - y1;
    const length = Math.max(1, Math.sqrt((dx * dx) + (dy * dy)));
    const angle = Math.atan2(dy, dx);
    return {
      left: ((x1 + x2) / 2) - (length / 2),
      top: ((y1 + y2) / 2) - 1,
      width: length,
      angle,
    };
  }, [currentLocationKey, mapSize.height, mapSize.width, selectedTravelOption]);

  const handleMapLayout = (event: LayoutChangeEvent) => {
    const nextWidth = Math.max(0, Math.round(event.nativeEvent.layout.width || 0));
    const nextHeight = Math.max(0, Math.round(event.nativeEvent.layout.height || 0));
    if (nextWidth === mapSize.width && nextHeight === mapSize.height) return;
    setMapSize({ width: nextWidth, height: nextHeight });
  };

  const startTravel = async () => {
    if (!selectedTravelOption || !executionGuard.allowed || traveling) return;

    setTraveling(true);
    routeAnim.setValue(0);
    await new Promise<void>((resolve) => {
      Animated.timing(routeAnim, {
        toValue: 1,
        duration: 360,
        useNativeDriver: true,
      }).start(() => resolve());
    });
    await new Promise<void>((resolve) => {
      setTimeout(() => resolve(), 240);
    });

    const ok = await loop.executeAction({
      action_key: 'travel',
      title: `Travel to ${selectedTravelOption.destination_label}`,
      description: `Travel from ${selectedTravelOption.from_label} to ${selectedTravelOption.destination_label}.`,
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'high',
      parameters: {
        destination_key: selectedTravelOption.destination_key,
        time_cost_units: Number(selectedTravelOption.time_cost_units || 0),
      },
    });
    if (ok) {
      setSelectedDestinationKey(null);
    }
    setTraveling(false);
  };

  const detailsOpacity = detailsAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 1] });
  const detailsTranslateY = detailsAnim.interpolate({ inputRange: [0, 1], outputRange: [8, 0] });
  const routeOpacity = routeAnim.interpolate({ inputRange: [0, 1], outputRange: [0.25, 1] });

  return (
    <GameplayLoopScaffold
      title="City Map"
      subtitle="Travel strategically to trade time for better opportunities"
      activeNavKey="map"
      footer={(
        <GameplayStickyActionArea
          summary={`Current location: ${currentLocationLabel}`}
          secondaryLabel="Back To Dashboard"
          onSecondaryPress={() => { onboarding.navigateTo('dashboard'); }}
          primaryLabel="Open Work"
          onPrimaryPress={() => { onboarding.navigateTo('work'); }}
        />
      )}
    >
      <GameplaySummaryCard eyebrow="Position" title="Current Location">
        <GameplayCompactMetricRows
          items={[
            { label: 'Current location', value: currentLocationLabel, tone: 'info' },
            { label: 'Region', value: currentLocationRegion },
            { label: 'Time left today', value: `${loop.dailySession.remainingTimeUnits}/${loop.dailySession.totalTimeUnits}` },
            { label: 'Trips today', value: `${Math.round(Number(workState?.rideshare_state?.trips_today || 0))}/${Math.round(Number(workState?.rideshare_state?.max_trips || 6))}` },
          ]}
        />
      </GameplaySummaryCard>

      <GameplaySummaryCard eyebrow="Map" title="Houston Strategy Map">
        <View style={styles.legendRow}>
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: theme.ui.positive }]} />
            <Text style={styles.legendLabel}>High opportunity</Text>
          </View>
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: theme.ui.warning }]} />
            <Text style={styles.legendLabel}>Calmer / lower payout</Text>
          </View>
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: theme.ui.danger }]} />
            <Text style={styles.legendLabel}>Higher pressure</Text>
          </View>
        </View>

        <View style={styles.mapCanvas} onLayout={handleMapLayout}>
          <View style={styles.regionSuburban}>
            <Text style={styles.regionTitle}>Suburban</Text>
            <Text style={styles.regionSub}>Calmer flow</Text>
          </View>
          <View style={styles.regionDowntown}>
            <Text style={styles.regionTitle}>Downtown</Text>
            <Text style={styles.regionSub}>Higher demand</Text>
          </View>

          {routeGeometry ? (
            <Animated.View
              style={[
                styles.routeLine,
                {
                  left: routeGeometry.left,
                  top: routeGeometry.top,
                  width: routeGeometry.width,
                  opacity: routeOpacity,
                  transform: [
                    { rotate: `${routeGeometry.angle}rad` },
                    { scaleX: routeAnim },
                  ],
                },
              ]}
            />
          ) : null}

          {nodes.map((node) => {
            const layout = PIN_LAYOUT[String(node.key)];
            if (!layout) return null;
            const isCurrent = String(node.key) === currentLocationKey;
            const isSelected = String(node.key) === selectedDestinationKey;
            return (
              <Pressable
                key={String(node.key)}
                style={[
                  styles.pinWrap,
                  { left: `${layout.x}%`, top: `${layout.y}%` },
                ]}
                onPress={() => {
                  if (isCurrent) {
                    setSelectedDestinationKey(null);
                    return;
                  }
                  setSelectedDestinationKey(String(node.key));
                }}
              >
                <Animated.View
                  style={[
                    styles.pin,
                    {
                      backgroundColor: colorForOpportunity(String(node.opportunity_tier || 'moderate')),
                      borderColor: isCurrent ? theme.ui.info : isSelected ? theme.ui.action : theme.ui.bg.sheet,
                      transform: [{ scale: isCurrent ? Animated.multiply(pulseAnim, arrivalAnim) : 1 }],
                    },
                  ]}
                />
                <Text style={styles.pinLabel}>
                  {String(node.label)}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </GameplaySummaryCard>

      {selectedTravelOption ? (
        <Animated.View style={{ opacity: detailsOpacity, transform: [{ translateY: detailsTranslateY }] }}>
          <GameplaySummaryCard eyebrow="Travel Preview" title={selectedTravelOption.destination_label}>
            <GameplayCompactMetricRows
              items={[
                { label: 'From', value: selectedTravelOption.from_label },
                { label: 'To', value: selectedTravelOption.destination_label },
                { label: 'Region', value: selectedTravelOption.destination_region },
                {
                  label: 'Travel time',
                  value: `${selectedTravelOption.time_cost_units} time unit${selectedTravelOption.time_cost_units === 1 ? '' : 's'}`,
                  tone: selectedTravelOption.time_cost_units >= 2 ? 'warning' : 'info',
                },
                {
                  label: 'Travel stress',
                  value: `${selectedTravelOption.stress_delta >= 0 ? '+' : ''}${selectedTravelOption.stress_delta}`,
                  tone: selectedTravelOption.stress_delta > 0 ? 'warning' : 'neutral',
                },
                {
                  label: 'Travel cost',
                  value: formatMoney(selectedTravelOption.cash_cost_xgp),
                  tone: selectedTravelOption.cash_cost_xgp > 0 ? 'warning' : 'neutral',
                },
                {
                  label: 'Rideshare quality',
                  value: selectedTravelOption.rideshare_quality,
                  tone: toneForOpportunity(selectedTravelOption.destination_opportunity_tier),
                },
                { label: 'Actions there', value: actionsForNode(selectedTravelOption.destination_node_type) },
              ]}
            />

            {!executionGuard.allowed ? (
              <GameplayWarningBanner
                title="Travel blocked"
                message={executionGuard.reason || 'Travel is not available right now.'}
                tone="warning"
              />
            ) : null}

            <PrimaryButton
              label={traveling ? 'Traveling...' : `Travel (${selectedTravelOption.time_cost_units}u)`}
              onPress={() => { void startTravel(); }}
              disabled={!executionGuard.allowed || traveling || loop.executingAction}
            />
          </GameplaySummaryCard>
        </Animated.View>
      ) : (
        <GameplayWarningBanner
          title="Pick a destination"
          message="Tap a location pin to preview travel time, stress, cost, and local opportunities."
          tone="info"
        />
      )}
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  legendRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.xs,
  },
  legendDot: {
    width: 10,
    height: 10,
    borderRadius: 999,
  },
  legendLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  mapCanvas: {
    position: 'relative',
    height: 300,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    borderColor: theme.color.border,
    backgroundColor: theme.ui.bg.sheet,
    overflow: 'hidden',
  },
  regionSuburban: {
    position: 'absolute',
    left: '4%',
    top: '8%',
    width: '44%',
    height: '84%',
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    borderColor: theme.ui.bg.sheet,
    backgroundColor: theme.ui.bg.sheet,
    padding: theme.spacing.sm,
  },
  regionDowntown: {
    position: 'absolute',
    right: '4%',
    top: '8%',
    width: '44%',
    height: '84%',
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    borderColor: theme.ui.info,
    backgroundColor: theme.ui.bg.sheet,
    padding: theme.spacing.sm,
  },
  regionTitle: {
    ...theme.typography.label,
    color: theme.color.textPrimary,
  },
  regionSub: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  routeLine: {
    position: 'absolute',
    height: 2,
    backgroundColor: theme.ui.info,
    borderRadius: 999,
  },
  pinWrap: {
    position: 'absolute',
    width: 98,
    marginLeft: -14,
    marginTop: -10,
    alignItems: 'flex-start',
  },
  pin: {
    width: 14,
    height: 14,
    borderRadius: 999,
    borderWidth: 2,
  },
  pinLabel: {
    marginTop: 2,
    ...theme.typography.caption,
    color: theme.color.textPrimary,
    maxWidth: 96,
  },
});

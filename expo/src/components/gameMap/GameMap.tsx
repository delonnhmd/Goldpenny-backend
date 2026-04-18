import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  runOnJS,
  useAnimatedReaction,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import type { SharedValue } from 'react-native-reanimated';

import { alpha, theme } from '@/design/theme';

import type { SandboxCityMap, SandboxDistrict, SandboxMapTile } from './mapData';

interface GameMapProps {
  map: SandboxCityMap;
  selectedTileKey: string | null;
  onTileSelect: (tile: SandboxMapTile) => void;
  onZoomChange?: (zoom: number) => void;
  ownedTileKeys?: string[];
  developedTileKeys?: string[];
}

const MIN_SCALE = 0.9;
const MAX_SCALE = 2.8;
const CAMERA_PADDING = 16;
// Step 96N - zoom tiers drive interaction density.
// far (< 1.15): district overview
// medium (1.15-2.0): building / lot selection
// close (> 2.0): tile-slot precision
const ZOOM_TIER_MEDIUM = 1.15;
const ZOOM_TIER_CLOSE = 2.0;

function districtPalette(district: SandboxDistrict | null | undefined) {
  if (district?.tone === 'downtown') return theme.gameUi.district.downtown;
  if (district?.tone === 'commercial') return theme.gameUi.district.commercial;
  return theme.gameUi.district.suburban;
}

function tileVisualState(
  tile: SandboxMapTile,
  district: SandboxDistrict | null | undefined,
  isOwned: boolean,
  isDeveloped: boolean,
  isSelected: boolean,
  isCurrent: boolean,
) {
  const palette = districtPalette(district);
  const opportunityTier = String(tile.opportunityTier || '').toLowerCase();
  const trafficScore = Number(tile.landProfile?.trafficScore || 0);
  const landValue = Number(tile.landProfile?.valueXgp || 0);
  const isHighDemand = opportunityTier === 'high'
    || trafficScore >= 78
    || tile.actionTags.includes('rideshare')
    || tile.actionTags.includes('work_shift');
  const isHighProfit = isOwned
    || isDeveloped
    || landValue >= 520
    || (tile.kind === 'existing_business' && !tile.actionTags.includes('rideshare'));
  const isLowActivity = opportunityTier === 'low'
    || (tile.kind === 'empty_lot' && trafficScore > 0 && trafficScore < 48)
    || tile.kind === 'expansion_node';

  let backgroundColor: string = alpha(palette.accent, district?.tone === 'downtown' ? 0.24 : 0.16);
  let borderColor: string = alpha(palette.accent, district?.tone === 'downtown' ? 0.6 : 0.48);
  let labelColor: string = district?.tone === 'downtown' ? palette.label : theme.gameUi.textPrimary;
  let signalColor: string = theme.gameUi.icons.neutral;

  switch (tile.kind) {
    case 'road':
      backgroundColor = theme.gameUi.road;
      borderColor = alpha(theme.gameUi.road, 0.92);
      labelColor = theme.gameUi.card;
      signalColor = theme.gameUi.icons.neutral;
      break;
    case 'building_slot':
      backgroundColor = alpha(theme.gameUi.icons.openSlot, 0.22);
      borderColor = alpha(theme.gameUi.icons.openSlot, 0.82);
      labelColor = theme.gameUi.textPrimary;
      signalColor = theme.gameUi.icons.openSlot;
      break;
    case 'existing_business':
      backgroundColor = alpha(theme.gameUi.icons.neutral, 0.18);
      borderColor = alpha(theme.gameUi.icons.neutral, 0.78);
      labelColor = theme.gameUi.textPrimary;
      signalColor = theme.gameUi.icons.neutral;
      break;
    case 'service_building':
      backgroundColor = alpha(theme.gameUi.primary, district?.tone === 'downtown' ? 0.34 : 0.16);
      borderColor = alpha(theme.gameUi.primary, 0.8);
      labelColor = district?.tone === 'downtown' ? theme.gameUi.card : theme.gameUi.textPrimary;
      signalColor = theme.gameUi.primary;
      break;
    case 'expansion_node':
      backgroundColor = alpha(theme.gameUi.signals.lowActivity, 0.12);
      borderColor = alpha(theme.gameUi.signals.lowActivity, 0.42);
      labelColor = theme.gameUi.textSecondary;
      signalColor = theme.gameUi.icons.neutral;
      break;
    default:
      break;
  }

  if (isLowActivity) {
    backgroundColor = alpha(theme.gameUi.signals.lowActivity, tile.kind === 'expansion_node' ? 0.16 : 0.1);
    borderColor = alpha(theme.gameUi.signals.lowActivity, 0.34);
    labelColor = theme.gameUi.textSecondary;
    signalColor = theme.gameUi.icons.neutral;
  }

  if (isHighProfit) {
    backgroundColor = alpha(theme.gameUi.signals.profit, isDeveloped ? 0.34 : 0.22);
    borderColor = alpha(theme.gameUi.signals.profit, 0.84);
    labelColor = theme.gameUi.textPrimary;
    signalColor = theme.gameUi.icons.ownedBusiness;
  }

  if (isOwned) {
    backgroundColor = alpha(theme.gameUi.success, 0.24);
    borderColor = theme.gameUi.success;
    labelColor = theme.gameUi.textPrimary;
    signalColor = theme.gameUi.icons.ownedBusiness;
  }

  if (isHighDemand) {
    borderColor = alpha(theme.gameUi.signals.demand, 0.88);
    signalColor = theme.gameUi.icons.hotspot;
  }

  if (isSelected) {
    backgroundColor = alpha(theme.gameUi.primary, 0.18);
    borderColor = theme.gameUi.primary;
    labelColor = theme.gameUi.textPrimary;
    signalColor = theme.gameUi.primary;
  }

  if (isCurrent) {
    borderColor = theme.gameUi.primary;
    labelColor = theme.gameUi.textPrimary;
    signalColor = theme.gameUi.icons.player;
  }

  return {
    backgroundColor,
    borderColor,
    labelColor,
    signalColor,
    isHighDemand,
    isHighProfit,
    isLowActivity,
  };
}

function SignalPulse({
  color,
  progress,
}: {
  color: string;
  progress: SharedValue<number>;
}) {
  const haloStyle = useAnimatedStyle(() => ({
    opacity: 0.16 + (progress.value * 0.18),
    transform: [{ scale: 0.82 + (progress.value * 0.32) }],
  }));

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.signalPulse,
        {
          backgroundColor: alpha(color, 0.18),
          borderColor: alpha(color, 0.62),
          shadowColor: color,
        },
        haloStyle,
      ]}
    />
  );
}

export function zoomTierFor(scale: number): 'far' | 'medium' | 'close' {
  if (scale < ZOOM_TIER_MEDIUM) return 'far';
  if (scale < ZOOM_TIER_CLOSE) return 'medium';
  return 'close';
}

function clamp(value: number, min: number, max: number): number {
  'worklet';
  return Math.min(max, Math.max(min, value));
}

function clampTranslation(translate: number, viewport: number, content: number, scale: number): number {
  'worklet';
  const scaledContent = content * scale;
  if (scaledContent <= viewport) {
    return (viewport - scaledContent) / 2;
  }
  const minTranslate = viewport - scaledContent - CAMERA_PADDING;
  const maxTranslate = CAMERA_PADDING;
  return clamp(translate, minTranslate, maxTranslate);
}

export default function GameMap({
  map,
  selectedTileKey,
  onTileSelect,
  onZoomChange,
  ownedTileKeys = [],
  developedTileKeys = [],
}: GameMapProps) {
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const initializedRef = useRef(false);

  const scale = useSharedValue(1);
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const startScale = useSharedValue(1);
  const startTranslateX = useSharedValue(0);
  const startTranslateY = useSharedValue(0);
  const viewportWidth = useSharedValue(0);
  const viewportHeight = useSharedValue(0);
  const hotspotPulse = useSharedValue(0);

  const districtByKey = useMemo(
    () => Object.fromEntries(map.districts.map((district) => [district.key, district])),
    [map.districts],
  ) as Record<string, SandboxDistrict>;

  const selectedTile = selectedTileKey ? map.tileByKey[selectedTileKey] || null : null;
  const currentTile = map.currentLocationTileKey ? map.tileByKey[map.currentLocationTileKey] || null : null;

  useEffect(() => {
    hotspotPulse.value = withRepeat(withTiming(1, { duration: 1400 }), -1, true);
  }, [hotspotPulse]);

  const centerOnTile = useCallback((tile: SandboxMapTile | null, nextScale = scale.value) => {
    if (!tile || viewport.width <= 0 || viewport.height <= 0) return;
    const tileCenterX = (tile.x * map.tileSize) + (map.tileSize / 2);
    const tileCenterY = (tile.y * map.tileSize) + (map.tileSize / 2);
    const rawTranslateX = (viewport.width / 2) - (tileCenterX * nextScale);
    const rawTranslateY = (viewport.height / 2) - (tileCenterY * nextScale);
    const clampedX = clampTranslation(rawTranslateX, viewport.width, map.worldWidth, nextScale);
    const clampedY = clampTranslation(rawTranslateY, viewport.height, map.worldHeight, nextScale);
    scale.value = withTiming(nextScale, { duration: 180 });
    translateX.value = withTiming(clampedX, { duration: 180 });
    translateY.value = withTiming(clampedY, { duration: 180 });
  }, [map.tileSize, map.worldHeight, map.worldWidth, scale, translateX, translateY, viewport.height, viewport.width]);

  const adjustZoom = useCallback((delta: number) => {
    if (viewport.width <= 0 || viewport.height <= 0) return;
    const nextScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.value + delta));
    const focalX = viewport.width / 2;
    const focalY = viewport.height / 2;
    const worldFocalX = (focalX - translateX.value) / scale.value;
    const worldFocalY = (focalY - translateY.value) / scale.value;
    const rawTranslateX = focalX - (worldFocalX * nextScale);
    const rawTranslateY = focalY - (worldFocalY * nextScale);

    scale.value = withTiming(nextScale, { duration: 180 });
    translateX.value = withTiming(
      clampTranslation(rawTranslateX, viewport.width, map.worldWidth, nextScale),
      { duration: 180 },
    );
    translateY.value = withTiming(
      clampTranslation(rawTranslateY, viewport.height, map.worldHeight, nextScale),
      { duration: 180 },
    );
  }, [map.worldHeight, map.worldWidth, scale, translateX, translateY, viewport.height, viewport.width]);

  const handleTapCoordinate = useCallback((tileX: number, tileY: number) => {
    const tile = map.tileByCoordinate[`${tileX}:${tileY}`];
    if (tile) {
      onTileSelect(tile);
    }
  }, [map.tileByCoordinate, onTileSelect]);

  const panGesture = useMemo(() => Gesture.Pan()
    .onStart(() => {
      startTranslateX.value = translateX.value;
      startTranslateY.value = translateY.value;
    })
    .onUpdate((event) => {
      translateX.value = clampTranslation(
        startTranslateX.value + event.translationX,
        viewportWidth.value,
        map.worldWidth,
        scale.value,
      );
      translateY.value = clampTranslation(
        startTranslateY.value + event.translationY,
        viewportHeight.value,
        map.worldHeight,
        scale.value,
      );
    }), [map.worldHeight, map.worldWidth, scale, startTranslateX, startTranslateY, translateX, translateY, viewportHeight, viewportWidth]);

  const pinchGesture = useMemo(() => Gesture.Pinch()
    .onStart(() => {
      startScale.value = scale.value;
      startTranslateX.value = translateX.value;
      startTranslateY.value = translateY.value;
    })
    .onUpdate((event) => {
      const nextScale = clamp(startScale.value * event.scale, MIN_SCALE, MAX_SCALE);
      const worldFocalX = (event.focalX - startTranslateX.value) / startScale.value;
      const worldFocalY = (event.focalY - startTranslateY.value) / startScale.value;
      const rawTranslateX = event.focalX - (worldFocalX * nextScale);
      const rawTranslateY = event.focalY - (worldFocalY * nextScale);

      scale.value = nextScale;
      translateX.value = clampTranslation(rawTranslateX, viewportWidth.value, map.worldWidth, nextScale);
      translateY.value = clampTranslation(rawTranslateY, viewportHeight.value, map.worldHeight, nextScale);
    }), [map.worldHeight, map.worldWidth, scale, startScale, startTranslateX, startTranslateY, translateX, translateY, viewportHeight, viewportWidth]);

  const tapGesture = useMemo(() => Gesture.Tap()
    .maxDistance(10)
    .onEnd((event) => {
      const worldX = (event.x - translateX.value) / scale.value;
      const worldY = (event.y - translateY.value) / scale.value;
      const tileX = Math.floor(worldX / map.tileSize);
      const tileY = Math.floor(worldY / map.tileSize);
      if (tileX < 0 || tileY < 0 || tileX >= map.columns || tileY >= map.rows) return;
      runOnJS(handleTapCoordinate)(tileX, tileY);
    }), [handleTapCoordinate, map.columns, map.rows, map.tileSize, scale, translateX, translateY]);

  const gesture = useMemo(
    () => Gesture.Simultaneous(panGesture, pinchGesture, tapGesture),
    [panGesture, pinchGesture, tapGesture],
  );

  useAnimatedReaction(
    () => Number(scale.value.toFixed(2)),
    (current, previous) => {
      if (current === previous || !onZoomChange) return;
      runOnJS(onZoomChange)(current);
    },
    [onZoomChange, scale],
  );

  useEffect(() => {
    if (!viewport.width || !viewport.height || initializedRef.current) return;
    initializedRef.current = true;
    centerOnTile(currentTile || selectedTile);
  }, [centerOnTile, currentTile, selectedTile, viewport.height, viewport.width]);

  const handleLayout = (event: LayoutChangeEvent) => {
    const width = Math.round(event.nativeEvent.layout.width);
    const height = Math.round(event.nativeEvent.layout.height);
    if (width <= 0 || height <= 0) return;
    setViewport({ width, height });
    viewportWidth.value = width;
    viewportHeight.value = height;
  };

  const mapAnimatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
      { scale: scale.value },
    ],
  }));

  return (
    <View style={styles.mapFrame} onLayout={handleLayout}>
      <View pointerEvents="none" style={styles.atmosphereLayer}>
        <View style={styles.atmosphereOrbPrimary} />
        <View style={styles.atmosphereOrbSecondary} />
      </View>

      <GestureDetector gesture={gesture}>
        <View style={styles.viewport}>
          <Animated.View
            style={[
              styles.world,
              {
                width: map.worldWidth,
                height: map.worldHeight,
              },
              mapAnimatedStyle,
            ]}
          >
            {map.districts.map((district) => {
              const palette = districtPalette(district);
              return (
                <View
                  key={district.key}
                  style={[
                    styles.districtBlock,
                    {
                      left: district.x * map.tileSize,
                      top: district.y * map.tileSize,
                      width: district.width * map.tileSize,
                      height: district.height * map.tileSize,
                      backgroundColor: district.fill,
                      borderColor: alpha(district.accent, 0.92),
                    },
                  ]}
                >
                  <View
                    style={[
                      styles.districtBadge,
                      {
                        borderColor: alpha(district.accent, 0.84),
                        backgroundColor: palette.badgeBackground,
                      },
                    ]}
                  >
                    <Text style={[styles.districtTitle, { color: palette.label }]}>{district.label}</Text>
                    <Text style={[styles.districtSubtitle, { color: alpha(palette.label, 0.72) }]}>{district.subtitle}</Text>
                  </View>
                </View>
              );
            })}

            {map.tiles.map((tile) => {
              const isSelected = tile.key === selectedTileKey;
              const isCurrent = tile.isCurrentLocation;
              const isOwned = ownedTileKeys.includes(tile.key);
              const isDeveloped = developedTileKeys.includes(tile.key);
              const showLabel = tile.kind !== 'empty_lot' && tile.kind !== 'road';
              const district = tile.districtKey ? districtByKey[tile.districtKey] || null : null;
              const visual = tileVisualState(tile, district, isOwned, isDeveloped, isSelected, isCurrent);

              return (
                <View
                  key={tile.key}
                  style={[
                    styles.tile,
                    {
                      left: tile.x * map.tileSize,
                      top: tile.y * map.tileSize,
                      width: map.tileSize,
                      height: map.tileSize,
                      backgroundColor: visual.backgroundColor,
                      borderColor: visual.borderColor,
                    },
                    tile.kind === 'road' ? styles.tileRoad : null,
                    tile.kind === 'building_slot' ? styles.tileBuildable : null,
                    tile.kind === 'existing_business' ? styles.tileBusiness : null,
                    tile.kind === 'service_building' ? styles.tileService : null,
                    tile.kind === 'expansion_node' ? styles.tileExpansion : null,
                    isSelected ? styles.tileSelected : null,
                    isCurrent ? styles.tileCurrent : null,
                  ]}
                >
                  {visual.isLowActivity ? (
                    <View style={styles.lowActivityOverlay} pointerEvents="none" />
                  ) : null}

                  {visual.isHighDemand ? (
                    <SignalPulse color={theme.gameUi.signals.demand} progress={hotspotPulse} />
                  ) : null}

                  {visual.isHighProfit && !visual.isHighDemand ? (
                    <View
                      pointerEvents="none"
                      style={[
                        styles.profitHalo,
                        {
                          backgroundColor: alpha(theme.gameUi.signals.profit, 0.18),
                          borderColor: alpha(theme.gameUi.signals.profit, 0.6),
                        },
                      ]}
                    />
                  ) : null}

                  {tile.kind === 'road' ? (
                    <View
                      style={[
                        styles.roadStripe,
                        tile.roadAxis === 'vertical' ? styles.roadStripeVertical : null,
                        tile.roadAxis === 'intersection' ? styles.roadStripeIntersection : null,
                      ]}
                    />
                  ) : null}

                  {tile.kind === 'building_slot' ? <View style={styles.buildSlotInset} /> : null}

                  <View
                    style={[
                      styles.tileSignal,
                      {
                        backgroundColor: visual.signalColor,
                        shadowColor: visual.signalColor,
                      },
                    ]}
                  />

                  {showLabel ? (
                    <Text style={[styles.tileLabel, { color: visual.labelColor }]}>
                      {tile.shortLabel || tile.label.slice(0, 3).toUpperCase()}
                    </Text>
                  ) : null}

                  {isCurrent ? (
                    <View style={styles.currentMarker}>
                      <Text style={styles.currentMarkerText}>YOU</Text>
                    </View>
                  ) : null}
                </View>
              );
            })}
          </Animated.View>
        </View>
      </GestureDetector>

      <View style={styles.controls}>
        <Pressable style={styles.controlButton} onPress={() => adjustZoom(0.2)}>
          <Text style={styles.controlLabel}>+</Text>
        </Pressable>
        <Pressable style={styles.controlButton} onPress={() => adjustZoom(-0.2)}>
          <Text style={styles.controlLabel}>-</Text>
        </Pressable>
        <Pressable style={styles.controlButtonWide} onPress={() => centerOnTile(currentTile || selectedTile, 1)}>
          <Text style={styles.controlLabelWide}>Center</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  mapFrame: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: theme.gameUi.mapBackdrop,
  },
  atmosphereLayer: {
    ...StyleSheet.absoluteFillObject,
  },
  atmosphereOrbPrimary: {
    position: 'absolute',
    top: -36,
    left: -24,
    width: 180,
    height: 180,
    borderRadius: 999,
    backgroundColor: alpha(theme.gameUi.primary, 0.12),
  },
  atmosphereOrbSecondary: {
    position: 'absolute',
    right: -42,
    bottom: 76,
    width: 220,
    height: 220,
    borderRadius: 999,
    backgroundColor: alpha(theme.gameUi.signals.demand, 0.08),
  },
  viewport: {
    flex: 1,
    backgroundColor: theme.gameUi.mapBackdrop,
  },
  world: {
    position: 'absolute',
    left: 0,
    top: 0,
    backgroundColor: theme.gameUi.mapBackdropDeep,
  },
  districtBlock: {
    position: 'absolute',
    borderWidth: 2,
    shadowColor: theme.gameUi.primary,
    shadowOpacity: 0.08,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
  },
  districtBadge: {
    margin: 8,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 10,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  districtTitle: {
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  districtSubtitle: {
    marginTop: 1,
    ...theme.typography.caption,
    fontSize: 9,
    lineHeight: 11,
  },
  tile: {
    position: 'absolute',
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  tileRoad: {
    borderWidth: 0,
  },
  tileBuildable: {
    borderWidth: 1.5,
  },
  tileBusiness: {
    borderWidth: 1.5,
  },
  tileService: {
    borderWidth: 1.5,
  },
  tileExpansion: {
    borderStyle: 'dashed',
  },
  tileSelected: {
    borderWidth: 2,
    shadowColor: theme.gameUi.primary,
    shadowOpacity: 0.26,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
  },
  tileCurrent: {
    borderWidth: 2,
  },
  lowActivityOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: theme.gameUi.lowActivityOverlay,
  },
  signalPulse: {
    position: 'absolute',
    width: '72%',
    height: '72%',
    borderRadius: 999,
    borderWidth: 1,
    shadowOpacity: 0.18,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
  },
  profitHalo: {
    position: 'absolute',
    width: '64%',
    height: '64%',
    borderRadius: 999,
    borderWidth: 1,
  },
  tileSignal: {
    position: 'absolute',
    top: 4,
    right: 4,
    width: 7,
    height: 7,
    borderRadius: 999,
    shadowOpacity: 0.3,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 0 },
  },
  tileLabel: {
    ...theme.typography.caption,
    fontSize: 8,
    lineHeight: 9,
    fontWeight: '800',
    letterSpacing: 0.4,
    textAlign: 'center',
  },
  roadStripe: {
    position: 'absolute',
    width: '70%',
    height: 2,
    backgroundColor: theme.gameUi.roadStripe,
    borderRadius: 999,
  },
  roadStripeVertical: {
    width: 2,
    height: '70%',
  },
  roadStripeIntersection: {
    width: '70%',
    height: 2,
    borderRadius: 999,
  },
  buildSlotInset: {
    width: '60%',
    height: '60%',
    borderWidth: 1,
    borderColor: alpha(theme.gameUi.icons.openSlot, 0.46),
    borderRadius: 4,
    backgroundColor: alpha(theme.gameUi.card, 0.24),
  },
  currentMarker: {
    position: 'absolute',
    bottom: 2,
    left: 2,
    right: 2,
    paddingVertical: 1,
    borderRadius: 999,
    backgroundColor: alpha(theme.gameUi.primary, 0.94),
  },
  currentMarkerText: {
    color: theme.gameUi.card,
    fontSize: 6,
    lineHeight: 7,
    fontWeight: '900',
    textAlign: 'center',
    letterSpacing: 0.5,
  },
  controls: {
    position: 'absolute',
    right: 10,
    top: 10,
    gap: 6,
    alignItems: 'flex-end',
  },
  controlButton: {
    width: 40,
    height: 40,
    borderRadius: 14,
    backgroundColor: theme.gameUi.hudGlass,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: theme.gameUi.hudBorder,
    ...theme.shadow.md,
  },
  controlButtonWide: {
    minWidth: 68,
    height: 36,
    paddingHorizontal: 12,
    borderRadius: 14,
    backgroundColor: theme.gameUi.hudGlass,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: theme.gameUi.hudBorder,
    ...theme.shadow.md,
  },
  controlLabel: {
    fontSize: 22,
    lineHeight: 24,
    fontWeight: '700',
    color: theme.gameUi.textPrimary,
  },
  controlLabelWide: {
    ...theme.typography.caption,
    fontWeight: '800',
    color: theme.gameUi.textPrimary,
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
});

import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
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

function shouldShowTileLabel(tile: SandboxMapTile, isSelected: boolean, isCurrent: boolean): boolean {
  if (isSelected || isCurrent) return true;
  return tile.kind === 'service_building' || tile.kind === 'existing_business';
}

function shouldPulseDemand(tile: SandboxMapTile, isHighDemand: boolean): boolean {
  if (!isHighDemand) return false;
  return tile.kind === 'service_building'
    || tile.kind === 'existing_business'
    || Boolean(tile.nodeKey);
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
  const isHighDemand = (
    opportunityTier === 'high'
    || tile.actionTags.includes('rideshare')
    || tile.actionTags.includes('work_shift')
    || (Boolean(tile.nodeKey) && trafficScore >= 78)
  );
  const isHighProfit = (
    isOwned
    || isDeveloped
    || tile.kind === 'existing_business'
    || (tile.kind === 'building_slot' && landValue >= 520)
  );
  const isLowActivity = (
    tile.kind === 'expansion_node'
    || opportunityTier === 'low'
    || (tile.kind === 'empty_lot' && trafficScore > 0 && trafficScore < 48)
  );

  let backgroundColor: string = alpha(palette.accent, district?.tone === 'downtown' ? 0.24 : 0.16);
  let borderColor: string = alpha(palette.accent, district?.tone === 'downtown' ? 0.58 : 0.42);
  let labelColor: string = district?.tone === 'downtown' ? palette.label : theme.gameUi.textPrimary;

  switch (tile.kind) {
    case 'road':
      backgroundColor = theme.gameUi.road;
      borderColor = alpha(theme.gameUi.road, 0.94);
      labelColor = theme.gameUi.card;
      break;
    case 'building_slot':
      backgroundColor = alpha(theme.gameUi.icons.openSlot, 0.18);
      borderColor = alpha(theme.gameUi.icons.openSlot, 0.7);
      break;
    case 'existing_business':
      backgroundColor = alpha(theme.gameUi.icons.neutral, 0.16);
      borderColor = alpha(theme.gameUi.icons.neutral, 0.66);
      break;
    case 'service_building':
      backgroundColor = alpha(theme.gameUi.primary, district?.tone === 'downtown' ? 0.3 : 0.14);
      borderColor = alpha(theme.gameUi.primary, 0.76);
      labelColor = district?.tone === 'downtown' ? theme.gameUi.card : theme.gameUi.textPrimary;
      break;
    case 'expansion_node':
      backgroundColor = alpha(theme.gameUi.signals.lowActivity, 0.14);
      borderColor = alpha(theme.gameUi.signals.lowActivity, 0.36);
      labelColor = theme.gameUi.textSecondary;
      break;
    default:
      break;
  }

  if (isLowActivity) {
    backgroundColor = alpha(theme.gameUi.signals.lowActivity, tile.kind === 'expansion_node' ? 0.14 : 0.08);
    borderColor = alpha(theme.gameUi.signals.lowActivity, 0.28);
    labelColor = theme.gameUi.textSecondary;
  }

  if (isHighProfit) {
    backgroundColor = alpha(theme.gameUi.success, isDeveloped ? 0.28 : 0.18);
    borderColor = alpha(theme.gameUi.success, 0.8);
    labelColor = theme.gameUi.textPrimary;
  }

  if (isOwned) {
    backgroundColor = alpha(theme.gameUi.success, 0.24);
    borderColor = theme.gameUi.success;
  }

  if (isHighDemand) {
    borderColor = alpha(theme.gameUi.signals.demand, 0.84);
  }

  if (isSelected) {
    backgroundColor = alpha(theme.gameUi.primary, 0.16);
    borderColor = theme.gameUi.primary;
    labelColor = theme.gameUi.textPrimary;
  }

  if (isCurrent) {
    borderColor = theme.gameUi.primary;
    labelColor = theme.gameUi.textPrimary;
  }

  return {
    backgroundColor,
    borderColor,
    labelColor,
    isHighDemand,
    isHighProfit,
    isLowActivity,
  };
}

const SignalPulse = memo(function SignalPulse({
  color,
  progress,
}: {
  color: string;
  progress: SharedValue<number>;
}) {
  const haloStyle = useAnimatedStyle(() => ({
    opacity: 0.12 + (progress.value * 0.16),
    transform: [{ scale: 0.86 + (progress.value * 0.28) }],
  }));

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.signalPulse,
        {
          backgroundColor: alpha(color, 0.12),
          borderColor: alpha(color, 0.5),
        },
        haloStyle,
      ]}
    />
  );
});

const DistrictBlock = memo(function DistrictBlock({
  district,
  tileSize,
}: {
  district: SandboxDistrict;
  tileSize: number;
}) {
  const palette = districtPalette(district);

  return (
    <View
      style={[
        styles.districtBlock,
        {
          left: district.x * tileSize,
          top: district.y * tileSize,
          width: district.width * tileSize,
          height: district.height * tileSize,
          backgroundColor: district.fill,
          borderColor: alpha(district.accent, 0.88),
        },
      ]}
    >
      <View
        style={[
          styles.districtBadge,
          {
            borderColor: alpha(district.accent, 0.72),
            backgroundColor: palette.badgeBackground,
          },
        ]}
      >
        <Text style={[styles.districtTitle, { color: palette.label }]}>{district.label}</Text>
        <Text style={[styles.districtSubtitle, { color: alpha(palette.label, 0.72) }]}>{district.subtitle}</Text>
      </View>
    </View>
  );
});

const TileCell = memo(function TileCell({
  tile,
  tileSize,
  district,
  isSelected,
  isOwned,
  isDeveloped,
  hotspotPulse,
}: {
  tile: SandboxMapTile;
  tileSize: number;
  district: SandboxDistrict | null;
  isSelected: boolean;
  isOwned: boolean;
  isDeveloped: boolean;
  hotspotPulse: SharedValue<number>;
}) {
  const isCurrent = tile.isCurrentLocation;
  const visual = tileVisualState(tile, district, isOwned, isDeveloped, isSelected, isCurrent);
  const showLabel = shouldShowTileLabel(tile, isSelected, isCurrent);
  const showDemandPulse = shouldPulseDemand(tile, visual.isHighDemand);

  return (
    <View
      style={[
        styles.tile,
        {
          left: tile.x * tileSize,
          top: tile.y * tileSize,
          width: tileSize,
          height: tileSize,
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
      {showDemandPulse ? (
        <SignalPulse color={theme.gameUi.signals.demand} progress={hotspotPulse} />
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
}, (prev, next) => (
  prev.tile === next.tile
  && prev.tileSize === next.tileSize
  && prev.district === next.district
  && prev.isSelected === next.isSelected
  && prev.isOwned === next.isOwned
  && prev.isDeveloped === next.isDeveloped
  && prev.hotspotPulse === next.hotspotPulse
));

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

function GameMapComponent({
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
  const ownedTileSet = useMemo(() => new Set(ownedTileKeys), [ownedTileKeys]);
  const developedTileSet = useMemo(() => new Set(developedTileKeys), [developedTileKeys]);

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
            {map.districts.map((district) => (
              <DistrictBlock
                key={district.key}
                district={district}
                tileSize={map.tileSize}
              />
            ))}

            {map.tiles.map((tile) => (
              <TileCell
                key={tile.key}
                tile={tile}
                tileSize={map.tileSize}
                district={tile.districtKey ? districtByKey[tile.districtKey] || null : null}
                isSelected={tile.key === selectedTileKey}
                isOwned={ownedTileSet.has(tile.key)}
                isDeveloped={developedTileSet.has(tile.key)}
                hotspotPulse={hotspotPulse}
              />
            ))}
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
    backgroundColor: alpha(theme.gameUi.primary, 0.1),
  },
  atmosphereOrbSecondary: {
    position: 'absolute',
    right: -42,
    bottom: 76,
    width: 220,
    height: 220,
    borderRadius: 999,
    backgroundColor: alpha(theme.gameUi.signals.demand, 0.06),
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
  },
  tileCurrent: {
    borderWidth: 2,
  },
  signalPulse: {
    position: 'absolute',
    width: '72%',
    height: '72%',
    borderRadius: 999,
    borderWidth: 1,
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
    borderColor: alpha(theme.gameUi.icons.openSlot, 0.42),
    borderRadius: 4,
    backgroundColor: alpha(theme.gameUi.card, 0.18),
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

const GameMap = memo(GameMapComponent);

export default GameMap;

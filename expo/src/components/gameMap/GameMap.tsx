import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  runOnJS,
  useAnimatedReaction,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { theme } from '@/design/theme';

import type { SandboxCityMap, SandboxMapTile } from './mapData';

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
// Step 96N — zoom tiers drive interaction density.
// far (< 1.15): district overview
// medium (1.15–2.0): building / lot selection
// close (> 2.0): tile-slot precision
const ZOOM_TIER_MEDIUM = 1.15;
const ZOOM_TIER_CLOSE = 2.0;

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

  const selectedTile = selectedTileKey ? map.tileByKey[selectedTileKey] || null : null;
  const currentTile = map.currentLocationTileKey ? map.tileByKey[map.currentLocationTileKey] || null : null;

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

  const [currentZoomTier, setCurrentZoomTier] = useState<'far' | 'medium' | 'close'>('far');
  useAnimatedReaction(
    () => scale.value,
    (current) => {
      const tier = current < ZOOM_TIER_MEDIUM ? 'far' : current < ZOOM_TIER_CLOSE ? 'medium' : 'close';
      runOnJS(setCurrentZoomTier)(tier);
    },
    [scale],
  );
  const zoomHint = currentZoomTier === 'far'
    ? 'District overview. Zoom in to pick a lot.'
    : currentZoomTier === 'medium'
      ? 'Building / lot tier. Tap a tile to see options.'
      : 'Tile precision. Pick an exact frontage slot.';

  return (
    <View style={styles.mapFrame} onLayout={handleLayout}>
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
                    borderColor: district.accent,
                  },
                ]}
              >
                <View style={[styles.districtBadge, { borderColor: district.accent }]}>
                  <Text style={[styles.districtTitle, { color: district.accent }]}>{district.label}</Text>
                  <Text style={styles.districtSubtitle}>{district.subtitle}</Text>
                </View>
              </View>
            ))}

            {map.tiles.map((tile) => {
              const isSelected = tile.key === selectedTileKey;
              const isCurrent = tile.isCurrentLocation;
              const isOwned = ownedTileKeys.includes(tile.key);
              const isDeveloped = developedTileKeys.includes(tile.key);
              const showLabel = tile.kind !== 'empty_lot' && tile.kind !== 'road';

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
                    },
                    tile.kind === 'road' ? styles.tileRoad : null,
                    tile.kind === 'building_slot' ? styles.tileBuildable : null,
                    tile.kind === 'existing_business' ? styles.tileBusiness : null,
                    tile.kind === 'service_building' ? styles.tileService : null,
                    tile.kind === 'expansion_node' ? styles.tileExpansion : null,
                    isOwned ? styles.tileOwned : null,
                    isDeveloped ? styles.tileDeveloped : null,
                    isSelected ? styles.tileSelected : null,
                    isCurrent ? styles.tileCurrent : null,
                  ]}
                >
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
                    <Text style={styles.tileLabel}>{tile.shortLabel || tile.label.slice(0, 3).toUpperCase()}</Text>
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

      <View style={styles.overlayTop}>
        <View style={styles.overlayBadge}>
          <Text style={styles.overlayEyebrow}>Map Mode · {currentZoomTier.toUpperCase()}</Text>
          <Text style={styles.overlayText}>{zoomHint}</Text>
        </View>
      </View>

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
    borderRadius: 26,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(103, 232, 249, 0.18)',
    backgroundColor: '#08111f',
    shadowColor: '#020617',
    shadowOpacity: 0.34,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 12 },
    elevation: 10,
  },
  viewport: {
    flex: 1,
    backgroundColor: '#050b16',
  },
  world: {
    position: 'absolute',
    left: 0,
    top: 0,
    backgroundColor: '#060c18',
  },
  districtBlock: {
    position: 'absolute',
    borderWidth: 2,
    shadowColor: '#020617',
    shadowOpacity: 0.26,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
  },
  districtBadge: {
    margin: 8,
    paddingHorizontal: 6,
    paddingVertical: 5,
    borderRadius: 8,
    backgroundColor: 'rgba(6, 12, 24, 0.84)',
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
    color: '#94a3b8',
    fontSize: 9,
    lineHeight: 11,
  },
  tile: {
    position: 'absolute',
    borderWidth: 1,
    borderColor: 'rgba(51, 65, 85, 0.95)',
    backgroundColor: 'rgba(15, 23, 42, 0.72)',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  tileRoad: {
    backgroundColor: '#1f2937',
    borderColor: '#334155',
  },
  tileBuildable: {
    backgroundColor: 'rgba(34, 211, 238, 0.16)',
    borderColor: 'rgba(34, 211, 238, 0.45)',
  },
  tileBusiness: {
    backgroundColor: 'rgba(217, 119, 6, 0.9)',
    borderColor: '#fbbf24',
  },
  tileService: {
    backgroundColor: 'rgba(20, 184, 166, 0.7)',
    borderColor: '#67e8f9',
  },
  tileExpansion: {
    backgroundColor: 'rgba(71, 85, 105, 0.65)',
    borderColor: '#94a3b8',
  },
  tileSelected: {
    borderColor: '#67e8f9',
    borderWidth: 2,
    shadowColor: '#22d3ee',
    shadowOpacity: 0.55,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
    backgroundColor: 'rgba(14, 165, 233, 0.22)',
  },
  tileCurrent: {
    borderColor: '#f8fafc',
    borderWidth: 2,
  },
  tileOwned: {
    backgroundColor: 'rgba(34, 197, 94, 0.22)',
    borderColor: '#4ade80',
  },
  tileDeveloped: {
    backgroundColor: 'rgba(250, 204, 21, 0.32)',
    borderColor: '#fbbf24',
  },
  tileLabel: {
    ...theme.typography.caption,
    fontSize: 8,
    lineHeight: 9,
    fontWeight: '800',
    color: '#f8fafc',
    letterSpacing: 0.4,
  },
  roadStripe: {
    position: 'absolute',
    width: '70%',
    height: 2,
    backgroundColor: 'rgba(226, 232, 240, 0.36)',
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
    borderColor: 'rgba(103, 232, 249, 0.32)',
    borderRadius: 4,
    backgroundColor: 'rgba(15, 23, 42, 0.2)',
  },
  currentMarker: {
    position: 'absolute',
    bottom: 2,
    left: 2,
    right: 2,
    paddingVertical: 1,
    borderRadius: 3,
    backgroundColor: 'rgba(15, 23, 42, 0.84)',
  },
  currentMarkerText: {
    color: '#f8fafc',
    fontSize: 6,
    lineHeight: 7,
    fontWeight: '800',
    textAlign: 'center',
    letterSpacing: 0.5,
  },
  overlayTop: {
    position: 'absolute',
    left: 12,
    top: 12,
  },
  overlayBadge: {
    maxWidth: 230,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: 'rgba(6, 12, 24, 0.86)',
    borderWidth: 1,
    borderColor: 'rgba(103, 232, 249, 0.18)',
  },
  overlayEyebrow: {
    ...theme.typography.caption,
    color: '#67e8f9',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  overlayText: {
    marginTop: 2,
    ...theme.typography.bodySm,
    color: '#e2e8f0',
  },
  controls: {
    position: 'absolute',
    right: 12,
    top: 12,
    gap: 8,
    alignItems: 'flex-end',
  },
  controlButton: {
    width: 44,
    height: 44,
    borderRadius: 14,
    backgroundColor: 'rgba(8, 15, 30, 0.92)',
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.md,
    borderWidth: 1,
    borderColor: 'rgba(148, 163, 184, 0.16)',
  },
  controlButtonWide: {
    minWidth: 70,
    height: 38,
    paddingHorizontal: 12,
    borderRadius: 14,
    backgroundColor: 'rgba(8, 15, 30, 0.92)',
    alignItems: 'center',
    justifyContent: 'center',
    ...theme.shadow.md,
    borderWidth: 1,
    borderColor: 'rgba(148, 163, 184, 0.16)',
  },
  controlLabel: {
    fontSize: 24,
    lineHeight: 26,
    fontWeight: '700',
    color: '#f8fafc',
  },
  controlLabelWide: {
    ...theme.typography.caption,
    fontWeight: '800',
    color: '#f8fafc',
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
});

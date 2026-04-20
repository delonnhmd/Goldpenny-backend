import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  runOnJS,
  useAnimatedReaction,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';

import { alpha, theme } from '@/design/theme';

import type { RiverGeometry, SandboxCityMap, SandboxDistrict, SandboxMapTile } from './mapData';

interface GameMapProps {
  map: SandboxCityMap;
  selectedTileKey: string | null;
  onTileSelect: (tile: SandboxMapTile) => void;
  onZoomChange?: (zoom: number) => void;
  ownedTileKeys?: string[];
  developedTileKeys?: string[];
}

// Step 97F — wider zoom range. MIN_SCALE is small enough that the entire
// city silhouette fits inside a phone viewport with room to pan.
const MIN_SCALE = 0.32;
const MAX_SCALE = 3.4;
const CAMERA_PADDING = 12;

// Four zoom tiers (Step 97F). The tier value drives layer culling so each
// frame renders only what the user can read at that distance.
//   z1 (far)     : zones + roads + river. No tiles. No labels except zones.
//   z2 (medium)  : + tile clusters (fills, no borders). + district labels.
//   z3 (close)   : + tile borders. semantic states.
//   z4 (precise) : + numeric hints + per-tile short labels.
const Z_TIER_BREAKPOINTS = {
  medium: 0.55,
  close: 1.0,
  precise: 1.7,
};

export type ZoomTier = 'far' | 'medium' | 'close' | 'precise';

export function zoomTierFor(scale: number): ZoomTier {
  if (scale < Z_TIER_BREAKPOINTS.medium) return 'far';
  if (scale < Z_TIER_BREAKPOINTS.close) return 'medium';
  if (scale < Z_TIER_BREAKPOINTS.precise) return 'close';
  return 'precise';
}

const ROAD_BASE_COLOR = theme.gameUi.border;
const ROAD_CURB_COLOR = alpha(theme.gameUi.border, 0.55);
const TILE_FILL = theme.gameUi.cardRaised;
const TILE_BORDER = theme.gameUi.border;
const SELECTED_COLOR = theme.gameUi.primary;
const BUILD_READY_COLOR = theme.gameUi.icons.openSlot;

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

// Build a smooth quadratic-bezier path through the river anchors. Each
// anchor acts as a Q-control between midpoints of adjacent anchors so the
// centerline reads as a continuous curve rather than a polyline.
function riverPathFromGeometry(river: RiverGeometry): string {
  const pts = river.controlPoints;
  if (pts.length < 2) return '';
  const first = pts[0];
  const last = pts[pts.length - 1];
  let path = `M ${first.x.toFixed(1)} ${first.y.toFixed(1)}`;
  for (let i = 1; i < pts.length - 1; i += 1) {
    const ctrl = pts[i];
    const next = pts[i + 1];
    const midX = (ctrl.x + next.x) / 2;
    const midY = (ctrl.y + next.y) / 2;
    path += ` Q ${ctrl.x.toFixed(1)} ${ctrl.y.toFixed(1)} ${midX.toFixed(1)} ${midY.toFixed(1)}`;
  }
  path += ` T ${last.x.toFixed(1)} ${last.y.toFixed(1)}`;
  return path;
}

// Group consecutive same-axis road tiles along their cross-axis into
// rectangles so the static layer renders ~20 strips instead of hundreds of
// 16px squares.
interface RoadStrip { x: number; y: number; width: number; height: number }

function buildRoadStrips(map: SandboxCityMap): RoadStrip[] {
  const strips: RoadStrip[] = [];
  const tileSize = map.tileSize;

  // Horizontal strips: scan each row.
  for (let y = 0; y < map.rows; y += 1) {
    let runStart = -1;
    for (let x = 0; x <= map.columns; x += 1) {
      const tile = x < map.columns ? map.tileByCoordinate[`${x}:${y}`] : null;
      const isRoad = tile?.kind === 'road' && (tile.roadAxis === 'horizontal' || tile.roadAxis === 'intersection');
      if (isRoad && runStart === -1) runStart = x;
      if ((!isRoad || x === map.columns) && runStart !== -1) {
        strips.push({
          x: runStart * tileSize,
          y: y * tileSize,
          width: (x - runStart) * tileSize,
          height: tileSize,
        });
        runStart = -1;
      }
    }
  }

  // Vertical strips: scan each column. Skip cells already covered by a
  // horizontal strip's intersection — they will read identically.
  for (let x = 0; x < map.columns; x += 1) {
    let runStart = -1;
    for (let y = 0; y <= map.rows; y += 1) {
      const tile = y < map.rows ? map.tileByCoordinate[`${x}:${y}`] : null;
      const isRoad = tile?.kind === 'road' && (tile.roadAxis === 'vertical' || tile.roadAxis === 'intersection');
      if (isRoad && runStart === -1) runStart = y;
      if ((!isRoad || y === map.rows) && runStart !== -1) {
        strips.push({
          x: x * tileSize,
          y: runStart * tileSize,
          width: tileSize,
          height: (y - runStart) * tileSize,
        });
        runStart = -1;
      }
    }
  }

  return strips;
}

const StaticLayer = memo(function StaticLayer({ map }: { map: SandboxCityMap }) {
  const roadStrips = useMemo(() => buildRoadStrips(map), [map]);
  const riverPath = useMemo(() => riverPathFromGeometry(map.river), [map.river]);

  return (
    <View pointerEvents="none" style={[styles.layerFill, { width: map.worldWidth, height: map.worldHeight }]}>
      {map.districts.map((district) => (
        <View
          key={`zone_${district.key}`}
          style={[
            styles.zoneWash,
            {
              left: district.x * map.tileSize,
              top: district.y * map.tileSize,
              width: district.width * map.tileSize,
              height: district.height * map.tileSize,
              backgroundColor: district.fill,
            },
          ]}
        />
      ))}

      {roadStrips.map((strip, index) => (
        <View
          key={`road_${index}`}
          style={{
            position: 'absolute',
            left: strip.x,
            top: strip.y,
            width: strip.width,
            height: strip.height,
            backgroundColor: ROAD_BASE_COLOR,
            borderTopWidth: StyleSheet.hairlineWidth,
            borderBottomWidth: StyleSheet.hairlineWidth,
            borderColor: ROAD_CURB_COLOR,
          }}
        />
      ))}

      <Svg
        width={map.worldWidth}
        height={map.worldHeight}
        style={StyleSheet.absoluteFillObject}
        pointerEvents="none"
      >
        <Path
          d={riverPath}
          stroke={alpha(theme.gameUi.primary, 0.32)}
          strokeWidth={map.river.bandPx}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <Path
          d={riverPath}
          stroke={alpha(theme.gameUi.icons.openSlot, 0.7)}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
          opacity={0.7}
        />
      </Svg>
    </View>
  );
});

interface TileVisual {
  background: string;
  borderColor: string;
  borderWidth: number;
}

function tileVisual(
  tile: SandboxMapTile,
  isOwned: boolean,
  isDeveloped: boolean,
  isSelected: boolean,
): TileVisual {
  // Default: empty / lot.
  let background: string = TILE_FILL;
  let borderColor: string = TILE_BORDER;
  let borderWidth = 1;

  if (tile.kind === 'building_slot') {
    // build-ready: cardRaised + 12% info overlay, info border.
    background = alpha(BUILD_READY_COLOR, 0.12);
    borderColor = BUILD_READY_COLOR;
  } else if (tile.kind === 'existing_business') {
    background = alpha(theme.gameUi.success, 0.18);
    borderColor = theme.gameUi.success;
  } else if (tile.kind === 'service_building') {
    background = alpha(theme.gameUi.primary, 0.2);
    borderColor = theme.gameUi.primary;
  } else if (tile.kind === 'expansion_node') {
    background = alpha(theme.gameUi.signals.lowActivity, 0.1);
    borderColor = alpha(theme.gameUi.signals.lowActivity, 0.5);
  }

  if (tile.waterfront) {
    borderColor = alpha(theme.gameUi.icons.openSlot, 0.6);
  }

  if (isOwned) {
    background = alpha(theme.gameUi.success, 0.24);
    borderColor = theme.gameUi.success;
  }
  if (isDeveloped) {
    background = alpha(theme.gameUi.success, 0.32);
  }

  if (isSelected) {
    background = alpha(SELECTED_COLOR, 0.18);
    borderColor = SELECTED_COLOR;
    borderWidth = 2;
  }

  return { background, borderColor, borderWidth };
}

const TileCell = memo(function TileCell({
  tile,
  tileSize,
  showBorders,
  showLabel,
  isSelected,
  isOwned,
  isDeveloped,
}: {
  tile: SandboxMapTile;
  tileSize: number;
  showBorders: boolean;
  showLabel: boolean;
  isSelected: boolean;
  isOwned: boolean;
  isDeveloped: boolean;
}) {
  const visual = tileVisual(tile, isOwned, isDeveloped, isSelected);
  const showSelectionGlow = isSelected;
  return (
    <View
      style={{
        position: 'absolute',
        left: tile.x * tileSize,
        top: tile.y * tileSize,
        width: tileSize,
        height: tileSize,
        backgroundColor: visual.background,
        borderColor: showBorders || isSelected ? visual.borderColor : 'transparent',
        borderWidth: showBorders || isSelected ? visual.borderWidth : 0,
        borderRadius: 3,
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      {showSelectionGlow ? (
        <View
          pointerEvents="none"
          style={{
            position: 'absolute',
            left: -3,
            top: -3,
            right: -3,
            bottom: -3,
            borderRadius: 6,
            borderColor: alpha(SELECTED_COLOR, 0.3),
            borderWidth: 3,
          }}
        />
      ) : null}
      {showLabel && tile.shortLabel ? (
        <Text style={[styles.tileLabel, { color: theme.gameUi.textPrimary }]}>
          {tile.shortLabel}
        </Text>
      ) : null}
      {tile.isCurrentLocation ? (
        <View style={styles.currentMarker}>
          <Text style={styles.currentMarkerText}>YOU</Text>
        </View>
      ) : null}
    </View>
  );
}, (prev, next) => (
  prev.tile === next.tile
  && prev.tileSize === next.tileSize
  && prev.showBorders === next.showBorders
  && prev.showLabel === next.showLabel
  && prev.isSelected === next.isSelected
  && prev.isOwned === next.isOwned
  && prev.isDeveloped === next.isDeveloped
));

const TileLayer = memo(function TileLayer({
  map,
  tier,
  selectedTileKey,
  ownedTileSet,
  developedTileSet,
}: {
  map: SandboxCityMap;
  tier: ZoomTier;
  selectedTileKey: string | null;
  ownedTileSet: Set<string>;
  developedTileSet: Set<string>;
}) {
  // Drop road tiles — they are baked into StaticLayer as merged strips.
  // Drop river tiles — they are masked under the SVG ribbon.
  const renderable = useMemo(
    () => map.tiles.filter((t) => t.kind !== 'road' && t.zoneTone !== 'river'),
    [map.tiles],
  );

  const showBorders = tier === 'close' || tier === 'precise';
  const showLabel = tier === 'precise';

  return (
    <View pointerEvents="none" style={[styles.layerFill, { width: map.worldWidth, height: map.worldHeight }]}>
      {renderable.map((tile) => (
        <TileCell
          key={tile.key}
          tile={tile}
          tileSize={map.tileSize}
          showBorders={showBorders}
          showLabel={showLabel || tile.kind === 'service_building' || tile.kind === 'existing_business' || tile.key === selectedTileKey}
          isSelected={tile.key === selectedTileKey}
          isOwned={ownedTileSet.has(tile.key)}
          isDeveloped={developedTileSet.has(tile.key)}
        />
      ))}
    </View>
  );
});

const ZoneLabelsLayer = memo(function ZoneLabelsLayer({
  districts,
  tileSize,
  worldWidth,
  worldHeight,
}: {
  districts: SandboxDistrict[];
  tileSize: number;
  worldWidth: number;
  worldHeight: number;
}) {
  return (
    <View pointerEvents="none" style={[styles.layerFill, { width: worldWidth, height: worldHeight }]}>
      {districts.map((district) => (
        <View
          key={`label_${district.key}`}
          style={{
            position: 'absolute',
            left: (district.x * tileSize) + 8,
            top: (district.y * tileSize) + 8,
          }}
        >
          <Text
            style={{
              color: district.labelColor,
              fontSize: 10,
              fontWeight: '900',
              letterSpacing: 1.5,
              textTransform: 'uppercase',
            }}
          >
            {district.label}
          </Text>
        </View>
      ))}
    </View>
  );
});

function GameMapComponent({
  map,
  selectedTileKey,
  onTileSelect,
  onZoomChange,
  ownedTileKeys = [],
  developedTileKeys = [],
}: GameMapProps) {
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [tier, setTier] = useState<ZoomTier>('medium');
  const initializedRef = useRef(false);

  const scale = useSharedValue(1);
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const startScale = useSharedValue(1);
  const startTranslateX = useSharedValue(0);
  const startTranslateY = useSharedValue(0);
  const viewportWidth = useSharedValue(0);
  const viewportHeight = useSharedValue(0);

  const ownedTileSet = useMemo(() => new Set(ownedTileKeys), [ownedTileKeys]);
  const developedTileSet = useMemo(() => new Set(developedTileKeys), [developedTileKeys]);

  const selectedTile = selectedTileKey ? map.tileByKey[selectedTileKey] || null : null;
  const currentTile = map.currentLocationTileKey ? map.tileByKey[map.currentLocationTileKey] || null : null;

  const fitToWorldScale = useMemo(() => {
    if (viewport.width <= 0 || viewport.height <= 0) return MIN_SCALE;
    return Math.max(MIN_SCALE, Math.min(viewport.width / map.worldWidth, viewport.height / map.worldHeight) * 0.98);
  }, [map.worldHeight, map.worldWidth, viewport.height, viewport.width]);

  const centerOnTile = useCallback((tile: SandboxMapTile | null, nextScale = scale.value) => {
    if (!tile || viewport.width <= 0 || viewport.height <= 0) return;
    const tileCenterX = (tile.x * map.tileSize) + (map.tileSize / 2);
    const tileCenterY = (tile.y * map.tileSize) + (map.tileSize / 2);
    const rawTranslateX = (viewport.width / 2) - (tileCenterX * nextScale);
    const rawTranslateY = (viewport.height / 2) - (tileCenterY * nextScale);
    const clampedX = clampTranslation(rawTranslateX, viewport.width, map.worldWidth, nextScale);
    const clampedY = clampTranslation(rawTranslateY, viewport.height, map.worldHeight, nextScale);
    scale.value = withTiming(nextScale, { duration: 200 });
    translateX.value = withTiming(clampedX, { duration: 200 });
    translateY.value = withTiming(clampedY, { duration: 200 });
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

  const fitWorld = useCallback(() => {
    if (viewport.width <= 0 || viewport.height <= 0) return;
    const nextScale = fitToWorldScale;
    const rawTranslateX = (viewport.width - (map.worldWidth * nextScale)) / 2;
    const rawTranslateY = (viewport.height - (map.worldHeight * nextScale)) / 2;
    scale.value = withTiming(nextScale, { duration: 220 });
    translateX.value = withTiming(rawTranslateX, { duration: 220 });
    translateY.value = withTiming(rawTranslateY, { duration: 220 });
  }, [fitToWorldScale, map.worldHeight, map.worldWidth, scale, translateX, translateY, viewport.height, viewport.width]);

  // Tap target expansion: snap the tap point to the nearest selectable tile
  // within a small radius. Mobile fingers are wider than 16px so we accept
  // taps up to ~1.5 tiles away from a selectable cell.
  const handleTapCoordinate = useCallback((worldX: number, worldY: number) => {
    const baseTileX = Math.floor(worldX / map.tileSize);
    const baseTileY = Math.floor(worldY / map.tileSize);

    let best: SandboxMapTile | null = null;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let dy = -1; dy <= 1; dy += 1) {
      for (let dx = -1; dx <= 1; dx += 1) {
        const tx = baseTileX + dx;
        const ty = baseTileY + dy;
        if (tx < 0 || ty < 0 || tx >= map.columns || ty >= map.rows) continue;
        const tile = map.tileByCoordinate[`${tx}:${ty}`];
        if (!tile || !tile.selectable) continue;
        const cx = (tx + 0.5) * map.tileSize;
        const cy = (ty + 0.5) * map.tileSize;
        const dist = Math.hypot(cx - worldX, cy - worldY);
        if (dist < bestDistance) {
          bestDistance = dist;
          best = tile;
        }
      }
    }
    if (best) onTileSelect(best);
  }, [map.columns, map.rows, map.tileByCoordinate, map.tileSize, onTileSelect]);

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
      runOnJS(handleTapCoordinate)(worldX, worldY);
    }), [handleTapCoordinate, scale, translateX, translateY]);

  const gesture = useMemo(
    () => Gesture.Simultaneous(panGesture, pinchGesture, tapGesture),
    [panGesture, pinchGesture, tapGesture],
  );

  const handleTierChange = useCallback((nextTier: ZoomTier) => {
    setTier((current) => (current === nextTier ? current : nextTier));
    if (onZoomChange) {
      onZoomChange(nextTier === 'far' ? MIN_SCALE : nextTier === 'medium' ? Z_TIER_BREAKPOINTS.medium : nextTier === 'close' ? Z_TIER_BREAKPOINTS.close : Z_TIER_BREAKPOINTS.precise);
    }
  }, [onZoomChange]);

  // Animated reaction fires only on tier transitions, not every micro
  // scale update. This collapses pan/zoom redraws to a couple per gesture.
  useAnimatedReaction(
    () => {
      const s = scale.value;
      if (s < Z_TIER_BREAKPOINTS.medium) return 'far' as ZoomTier;
      if (s < Z_TIER_BREAKPOINTS.close) return 'medium' as ZoomTier;
      if (s < Z_TIER_BREAKPOINTS.precise) return 'close' as ZoomTier;
      return 'precise' as ZoomTier;
    },
    (current, previous) => {
      if (current === previous) return;
      runOnJS(handleTierChange)(current);
    },
    [handleTierChange],
  );

  useEffect(() => {
    if (!viewport.width || !viewport.height || initializedRef.current) return;
    initializedRef.current = true;
    if (currentTile || selectedTile) {
      centerOnTile(currentTile || selectedTile, 1.1);
    } else {
      fitWorld();
    }
  }, [centerOnTile, currentTile, fitWorld, selectedTile, viewport.height, viewport.width]);

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

  // Spec: at z1 hide tiles and labels entirely. District labels appear from z2 up.
  const showZoneLabels = tier !== 'far';
  const showTileLayer = tier !== 'far';

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
            <StaticLayer map={map} />
            {showTileLayer ? (
              <TileLayer
                map={map}
                tier={tier}
                selectedTileKey={selectedTileKey}
                ownedTileSet={ownedTileSet}
                developedTileSet={developedTileSet}
              />
            ) : null}
            {showZoneLabels ? (
              <ZoneLabelsLayer
                districts={map.districts}
                tileSize={map.tileSize}
                worldWidth={map.worldWidth}
                worldHeight={map.worldHeight}
              />
            ) : null}
          </Animated.View>
        </View>
      </GestureDetector>

      <View style={styles.controls}>
        <Pressable style={styles.controlButton} onPress={() => adjustZoom(0.25)}>
          <Text style={styles.controlLabel}>+</Text>
        </Pressable>
        <Pressable style={styles.controlButton} onPress={() => adjustZoom(-0.25)}>
          <Text style={styles.controlLabel}>-</Text>
        </Pressable>
        <Pressable style={styles.controlButtonWide} onPress={fitWorld}>
          <Text style={styles.controlLabelWide}>Fit</Text>
        </Pressable>
        <Pressable style={styles.controlButtonWide} onPress={() => centerOnTile(currentTile || selectedTile, 1.1)}>
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
    backgroundColor: theme.gameUi.background,
  },
  viewport: {
    flex: 1,
    backgroundColor: theme.gameUi.background,
  },
  world: {
    position: 'absolute',
    left: 0,
    top: 0,
    backgroundColor: theme.gameUi.background,
  },
  layerFill: {
    position: 'absolute',
    left: 0,
    top: 0,
  },
  zoneWash: {
    position: 'absolute',
  },
  tileLabel: {
    fontSize: 7,
    lineHeight: 8,
    fontWeight: '800',
    letterSpacing: 0.3,
    textAlign: 'center',
  },
  currentMarker: {
    position: 'absolute',
    bottom: 1,
    left: 1,
    right: 1,
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
    letterSpacing: 0.4,
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
    minWidth: 60,
    height: 34,
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

import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  interpolate,
  runOnJS,
  type SharedValue,
  useAnimatedReaction,
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, Line, Path, Rect } from 'react-native-svg';

import { alpha, theme } from '@/design/theme';

import type { SandboxCityMap, SandboxMapTile, SandboxRoadSegment, SandboxZoneWash } from './mapData';

interface GameMapProps {
  map: SandboxCityMap;
  selectedTileKey: string | null;
  onTileSelect: (tile: SandboxMapTile) => void;
  onZoomChange?: (zoom: number) => void;
  ownedTileKeys?: string[];
  developedTileKeys?: string[];
}

type MapZoomTier = 'z1' | 'z2' | 'z3' | 'z4';

const MIN_SCALE = 0.38;
const MAX_SCALE = 4;
const DEFAULT_SCALE = 0.92;
const CAMERA_PADDING = 18;
const ZOOM_LEVEL_ONE_MAX = 0.65;
const ZOOM_LEVEL_TWO_MAX = 1.2;
const ZOOM_LEVEL_THREE_MAX = 1.95;
const LOCATE_ME_SCALE = 1.6;
const PLAYER_MARKER_SIZE = 14;
const PLAYER_MARKER_PULSE_SIZE = 26;

function LocateMeIcon() {
  return (
    <Svg width={18} height={18} viewBox="0 0 24 24">
      <Line x1={12} y1={2.75} x2={12} y2={5.6} stroke={theme.ui.bg.sheet} strokeWidth={2.2} strokeLinecap="round" />
      <Line x1={12} y1={18.4} x2={12} y2={21.25} stroke={theme.ui.bg.sheet} strokeWidth={2.2} strokeLinecap="round" />
      <Line x1={2.75} y1={12} x2={5.6} y2={12} stroke={theme.ui.bg.sheet} strokeWidth={2.2} strokeLinecap="round" />
      <Line x1={18.4} y1={12} x2={21.25} y2={12} stroke={theme.ui.bg.sheet} strokeWidth={2.2} strokeLinecap="round" />
      <Circle cx={12} cy={12} r={4.4} stroke={theme.ui.bg.sheet} strokeWidth={2.2} fill="none" />
      <Circle cx={12} cy={12} r={1.2} fill={theme.ui.bg.sheet} />
    </Svg>
  );
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

export function zoomTierFor(scale: number): MapZoomTier {
  if (scale < ZOOM_LEVEL_ONE_MAX) return 'z1';
  if (scale < ZOOM_LEVEL_TWO_MAX) return 'z2';
  if (scale < ZOOM_LEVEL_THREE_MAX) return 'z3';
  return 'z4';
}

function shouldRenderTile(tile: SandboxMapTile, zoomTier: MapZoomTier): boolean {
  if (tile.kind === 'road') return false;
  if (zoomTier === 'z1') return false;
  if (zoomTier === 'z2') {
    if (tile.kind === 'service_building' || tile.kind === 'existing_business') return true;
    if (tile.waterfront && tile.buildable) return true;
    if (tile.buildable) return (tile.x + tile.y) % 3 === 0;
    return false;
  }
  return true;
}

function nearestTileForPoint(map: SandboxCityMap, worldX: number, worldY: number): SandboxMapTile | null {
  const baseX = Math.floor(worldX / map.tileSize);
  const baseY = Math.floor(worldY / map.tileSize);

  let best: { tile: SandboxMapTile; distance: number } | null = null;

  for (let dy = -2; dy <= 2; dy += 1) {
    for (let dx = -2; dx <= 2; dx += 1) {
      const tileX = baseX + dx;
      const tileY = baseY + dy;
      if (tileX < 0 || tileY < 0 || tileX >= map.columns || tileY >= map.rows) continue;
      const tile = map.tileByCoordinate[`${tileX}:${tileY}`];
      if (!tile || !tile.selectable) continue;
      const centerX = (tileX * map.tileSize) + (map.tileSize / 2);
      const centerY = (tileY * map.tileSize) + (map.tileSize / 2);
      const distance = ((centerX - worldX) ** 2) + ((centerY - worldY) ** 2);
      if (!best || distance < best.distance) {
        best = { tile, distance };
      }
    }
  }

  if (best) return best.tile;

  if (baseX < 0 || baseY < 0 || baseX >= map.columns || baseY >= map.rows) return null;
  return map.tileByCoordinate[`${baseX}:${baseY}`] || null;
}

function tileVisualState(
  tile: SandboxMapTile,
  isSelected: boolean,
  isOwned: boolean,
  isDeveloped: boolean,
) {
  let backgroundColor: string = theme.ui.bg.cardRaised;
  let borderColor: string = theme.ui.border;
  let borderWidth = 1;
  let labelColor: string = theme.ui.text.onDarkMuted;

  if (tile.buildable) {
    backgroundColor = alpha(theme.ui.info, tile.kind === 'building_slot' ? 0.16 : 0.1);
    borderColor = theme.ui.info;
    labelColor = theme.ui.text.onDark;
  }

  if (tile.waterfront && tile.buildable) {
    backgroundColor = alpha(theme.ui.info, 0.2);
    borderColor = alpha(theme.ui.info, 0.92);
  }

  if (tile.kind === 'existing_business' || isOwned || isDeveloped) {
    backgroundColor = alpha(theme.ui.positive, isDeveloped ? 0.28 : 0.2);
    borderColor = theme.ui.positive;
    labelColor = theme.ui.text.onDark;
  }

  if (tile.kind === 'service_building') {
    backgroundColor = alpha(theme.ui.action, 0.24);
    borderColor = alpha(theme.ui.action, 0.86);
    labelColor = theme.ui.text.onDark;
  }

  if (tile.kind === 'expansion_node') {
    backgroundColor = alpha(theme.ui.text.onDarkMuted, 0.12);
    borderColor = alpha(theme.ui.border, 0.82);
    labelColor = theme.ui.text.onDarkMuted;
  }

  if (tile.isCurrentLocation) {
    borderColor = theme.ui.action;
    borderWidth = 2;
    labelColor = theme.ui.text.onDark;
  }

  if (isSelected) {
    borderColor = theme.ui.action;
    borderWidth = 2;
    labelColor = theme.ui.text.onDark;
  }

  return {
    backgroundColor,
    borderColor,
    borderWidth,
    labelColor,
  };
}

const StaticLayer = memo(function StaticLayer({
  map,
  zoomTier,
}: {
  map: SandboxCityMap;
  zoomTier: MapZoomTier;
}) {
  const roads = useMemo(
    () => map.roads.filter((road) => (zoomTier === 'z1' ? road.major : true)),
    [map.roads, zoomTier],
  );

  const roadColor = alpha(theme.ui.border, 0.82);
  const curbColor = alpha(theme.ui.border, 0.98);

  return (
    <View pointerEvents="none" style={styles.staticLayer}>
      <Svg width={map.worldWidth} height={map.worldHeight}>
        <Rect
          x={0}
          y={0}
          width={map.worldWidth}
          height={map.worldHeight}
          fill={theme.ui.bg.card}
        />

        {map.zones.map((zone: SandboxZoneWash) => (
          <Rect
            key={zone.key}
            x={zone.x}
            y={zone.y}
            width={zone.width}
            height={zone.height}
            fill={zone.fill}
          />
        ))}

        {roads.map((road: SandboxRoadSegment) => {
          const horizontal = road.width >= road.height;
          return (
            <React.Fragment key={road.key}>
              <Rect
                x={road.x}
                y={road.y}
                width={road.width}
                height={road.height}
                fill={roadColor}
                rx={road.major ? 3 : 2}
              />
              {zoomTier !== 'z1' ? (
                <Rect
                  x={horizontal ? road.x : road.x + (road.width * 0.25)}
                  y={horizontal ? road.y + (road.height * 0.25) : road.y}
                  width={horizontal ? road.width : road.width * 0.5}
                  height={horizontal ? road.height * 0.5 : road.height}
                  fill={curbColor}
                  opacity={0.45}
                />
              ) : null}
            </React.Fragment>
          );
        })}

        <Path
          d={map.river.path}
          stroke={map.river.baseColor}
          strokeWidth={map.river.strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <Path
          d={map.river.path}
          stroke={map.river.highlightColor}
          strokeWidth={map.river.highlightWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.7}
          fill="none"
        />
      </Svg>
    </View>
  );
});

const TileCell = memo(function TileCell({
  tile,
  tileSize,
  zoomTier,
  isSelected,
  isOwned,
  isDeveloped,
}: {
  tile: SandboxMapTile;
  tileSize: number;
  zoomTier: MapZoomTier;
  isSelected: boolean;
  isOwned: boolean;
  isDeveloped: boolean;
}) {
  const visual = tileVisualState(tile, isSelected, isOwned, isDeveloped);
  const width = tileSize * tile.visualScaleX;
  const height = tileSize * tile.visualScaleY;
  const left = (tile.x * tileSize) + ((tileSize - width) / 2);
  const top = (tile.y * tileSize) + ((tileSize - height) / 2);
  const showTag = (
    tile.isCurrentLocation
    || isSelected
    || tile.kind === 'service_building'
    || tile.kind === 'existing_business'
    || (zoomTier === 'z4' && tile.kind === 'building_slot')
  );
  const showNumericHint = (
    zoomTier === 'z4'
    && Boolean(tile.landProfile)
    && tile.buildable
    && (isSelected || tile.kind === 'building_slot' || tile.waterfront)
  );

  return (
    <View
      pointerEvents="none"
      style={[
        styles.tile,
        {
          left,
          top,
          width,
          height,
          backgroundColor: visual.backgroundColor,
          borderColor: visual.borderColor,
          borderWidth: zoomTier === 'z2' ? 0 : visual.borderWidth,
          borderRadius: tile.zoneTone === 'rural' ? 3 : 2,
        },
      ]}
    >
      {isSelected ? <View style={styles.selectedGlow} /> : null}

      {showTag ? (
        <Text numberOfLines={1} style={[styles.tileTag, { color: visual.labelColor }]}>
          {tile.shortLabel || tile.label.slice(0, 3).toUpperCase()}
        </Text>
      ) : null}

      {showNumericHint ? (
        <Text numberOfLines={1} style={styles.tileHint}>
          {tile.landProfile ? `${tile.landProfile.trafficScore}` : ''}
        </Text>
      ) : null}
    </View>
  );
}, (prev, next) => (
  prev.tile === next.tile
  && prev.tileSize === next.tileSize
  && prev.zoomTier === next.zoomTier
  && prev.isSelected === next.isSelected
  && prev.isOwned === next.isOwned
  && prev.isDeveloped === next.isDeveloped
));

const TileLayer = memo(function TileLayer({
  map,
  zoomTier,
  selectedTileKey,
  ownedTileSet,
  developedTileSet,
}: {
  map: SandboxCityMap;
  zoomTier: MapZoomTier;
  selectedTileKey: string | null;
  ownedTileSet: Set<string>;
  developedTileSet: Set<string>;
}) {
  const visibleTiles = useMemo(
    () => map.tiles.filter((tile) => shouldRenderTile(tile, zoomTier)),
    [map.tiles, zoomTier],
  );

  if (zoomTier === 'z1') return null;

  return (
    <View pointerEvents="none" style={styles.tileLayer}>
      {visibleTiles.map((tile) => (
        <TileCell
          key={tile.key}
          tile={tile}
          tileSize={map.tileSize}
          zoomTier={zoomTier}
          isSelected={selectedTileKey === tile.key}
          isOwned={ownedTileSet.has(tile.key)}
          isDeveloped={developedTileSet.has(tile.key)}
        />
      ))}
    </View>
  );
});

const LabelLayer = memo(function LabelLayer({
  map,
  zoomTier,
}: {
  map: SandboxCityMap;
  zoomTier: MapZoomTier;
}) {
  if (zoomTier === 'z1') return null;

  const showNodeLabels = zoomTier === 'z4';

  return (
    <View pointerEvents="none" style={styles.labelLayer}>
      {map.zones.map((zone) => (
        <Text
          key={`zone_${zone.key}`}
          style={[
            styles.zoneLabel,
            {
              left: zone.labelX,
              top: zone.labelY,
              color: zone.labelColor,
            },
          ]}
        >
          {zone.label}
        </Text>
      ))}

      {showNodeLabels
        ? map.tiles
          .filter((tile) => tile.kind === 'service_building' || tile.kind === 'existing_business' || tile.isCurrentLocation)
          .map((tile) => (
            <Text
              key={`node_${tile.key}`}
              style={[
                styles.nodeLabel,
                {
                  left: (tile.x * map.tileSize) + 1,
                  top: (tile.y * map.tileSize) - 10,
                },
              ]}
            >
              {tile.label}
            </Text>
          ))
        : null}
    </View>
  );
});

const PlayerMarkerLayer = memo(function PlayerMarkerLayer({
  map,
  currentTile,
  pulse,
}: {
  map: SandboxCityMap;
  currentTile: SandboxMapTile | null;
  pulse: SharedValue<number>;
}) {
  const pulseStyle = useAnimatedStyle(() => ({
    opacity: interpolate(pulse.value, [0, 0.65, 1], [0, 0.28, 0]),
    transform: [{ scale: interpolate(pulse.value, [0, 1], [0.72, 1.6]) }],
  }));

  const coreStyle = useAnimatedStyle(() => ({
    transform: [{ scale: interpolate(pulse.value, [0, 0.5, 1], [1, 1.12, 1]) }],
  }));

  if (!currentTile) return null;

  const centerX = (currentTile.x * map.tileSize) + (map.tileSize / 2);
  const centerY = (currentTile.y * map.tileSize) + (map.tileSize / 2);

  return (
    <View
      pointerEvents="none"
      style={[
        styles.playerMarkerLayer,
        {
          left: centerX - (PLAYER_MARKER_SIZE / 2),
          top: centerY - (PLAYER_MARKER_SIZE / 2),
        },
      ]}
    >
      <Animated.View
        style={[
          styles.playerMarkerPulse,
          {
            left: -((PLAYER_MARKER_PULSE_SIZE - PLAYER_MARKER_SIZE) / 2),
            top: -((PLAYER_MARKER_PULSE_SIZE - PLAYER_MARKER_SIZE) / 2),
          },
          pulseStyle,
        ]}
      />
      <Animated.View style={[styles.playerMarkerCore, coreStyle]} />
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
  const [zoomTier, setZoomTier] = useState<MapZoomTier>(zoomTierFor(DEFAULT_SCALE));
  const initializedRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const pendingZoomRef = useRef<{ scale: number; tier: MapZoomTier } | null>(null);

  const scale = useSharedValue(DEFAULT_SCALE);
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const startScale = useSharedValue(DEFAULT_SCALE);
  const startTranslateX = useSharedValue(0);
  const startTranslateY = useSharedValue(0);
  const viewportWidth = useSharedValue(0);
  const viewportHeight = useSharedValue(0);
  const playerMarkerPulse = useSharedValue(0);

  const ownedTileSet = useMemo(() => new Set(ownedTileKeys), [ownedTileKeys]);
  const developedTileSet = useMemo(() => new Set(developedTileKeys), [developedTileKeys]);

  const selectedTile = selectedTileKey ? map.tileByKey[selectedTileKey] || null : null;
  const currentTile = map.currentLocationTileKey ? map.tileByKey[map.currentLocationTileKey] || null : null;

  const flushZoomSignal = useCallback(() => {
    rafRef.current = null;
    const pending = pendingZoomRef.current;
    if (!pending) return;
    pendingZoomRef.current = null;
    setZoomTier((current) => (current === pending.tier ? current : pending.tier));
    if (onZoomChange) {
      onZoomChange(Number(pending.scale.toFixed(2)));
    }
  }, [onZoomChange]);

  const queueZoomSignal = useCallback((nextScale: number) => {
    pendingZoomRef.current = {
      scale: nextScale,
      tier: zoomTierFor(nextScale),
    };
    if (rafRef.current != null) return;
    rafRef.current = requestAnimationFrame(flushZoomSignal);
  }, [flushZoomSignal]);

  useEffect(() => () => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
    }
  }, []);

  const pulseCurrentMarker = useCallback(() => {
    playerMarkerPulse.value = 0;
    playerMarkerPulse.value = withSequence(
      withTiming(1, { duration: 300 }),
      withTiming(0, { duration: 300 }),
    );
  }, [playerMarkerPulse]);

  const centerOnTile = useCallback((
    tile: SandboxMapTile | null,
    nextScale = scale.value,
    duration = 180,
  ) => {
    if (!tile || viewport.width <= 0 || viewport.height <= 0) return;
    const tileCenterX = (tile.x * map.tileSize) + (map.tileSize / 2);
    const tileCenterY = (tile.y * map.tileSize) + (map.tileSize / 2);
    const rawTranslateX = (viewport.width / 2) - (tileCenterX * nextScale);
    const rawTranslateY = (viewport.height / 2) - (tileCenterY * nextScale);
    const clampedX = clampTranslation(rawTranslateX, viewport.width, map.worldWidth, nextScale);
    const clampedY = clampTranslation(rawTranslateY, viewport.height, map.worldHeight, nextScale);
    scale.value = withTiming(nextScale, { duration });
    translateX.value = withTiming(clampedX, { duration });
    translateY.value = withTiming(clampedY, { duration });
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

  const handleLocateMe = useCallback(() => {
    const targetTile = currentTile || selectedTile;
    if (!targetTile) return;
    const nextScale = scale.value < ZOOM_LEVEL_TWO_MAX ? LOCATE_ME_SCALE : scale.value;
    centerOnTile(targetTile, nextScale, 240);
    pulseCurrentMarker();
  }, [centerOnTile, currentTile, pulseCurrentMarker, scale, selectedTile]);

  const handleTap = useCallback((worldX: number, worldY: number) => {
    const tile = nearestTileForPoint(map, worldX, worldY);
    if (tile) onTileSelect(tile);
  }, [map, onTileSelect]);

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
    .maxDistance(12)
    .onEnd((event) => {
      const worldX = (event.x - translateX.value) / scale.value;
      const worldY = (event.y - translateY.value) / scale.value;
      if (worldX < 0 || worldY < 0 || worldX > map.worldWidth || worldY > map.worldHeight) return;
      runOnJS(handleTap)(worldX, worldY);
    }), [handleTap, map.worldHeight, map.worldWidth, scale, translateX, translateY]);

  const gesture = useMemo(
    () => Gesture.Simultaneous(panGesture, pinchGesture, tapGesture),
    [panGesture, pinchGesture, tapGesture],
  );

  useAnimatedReaction(
    () => scale.value,
    (current, previous) => {
      if (previous !== null && Math.abs(current - previous) < 0.01) return;
      runOnJS(queueZoomSignal)(current);
    },
    [scale, queueZoomSignal],
  );

  useEffect(() => {
    if (!viewport.width || !viewport.height || initializedRef.current) return;
    initializedRef.current = true;
    centerOnTile(currentTile || selectedTile, DEFAULT_SCALE);
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
            <StaticLayer map={map} zoomTier={zoomTier} />
            <TileLayer
              map={map}
              zoomTier={zoomTier}
              selectedTileKey={selectedTileKey}
              ownedTileSet={ownedTileSet}
              developedTileSet={developedTileSet}
            />
            <LabelLayer map={map} zoomTier={zoomTier} />
            <PlayerMarkerLayer map={map} currentTile={currentTile} pulse={playerMarkerPulse} />
          </Animated.View>
        </View>
      </GestureDetector>

      <View style={styles.controls}>
        <Pressable style={styles.controlButton} onPress={() => adjustZoom(0.22)}>
          <Text style={styles.controlLabel}>+</Text>
        </Pressable>
        <Pressable style={styles.controlButton} onPress={() => adjustZoom(-0.22)}>
          <Text style={styles.controlLabel}>-</Text>
        </Pressable>
        <Pressable style={styles.controlButtonWide} onPress={() => centerOnTile(currentTile || selectedTile, DEFAULT_SCALE)}>
          <Text style={styles.controlLabelWide}>Center</Text>
        </Pressable>
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Locate current tile"
        disabled={!currentTile && !selectedTile}
        onPress={handleLocateMe}
        style={({ pressed }) => [
          styles.locateButton,
          pressed ? styles.locateButtonPressed : null,
          !currentTile && !selectedTile ? styles.locateButtonDisabled : null,
        ]}
      >
        <LocateMeIcon />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  mapFrame: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: theme.ui.bg.card,
  },
  viewport: {
    flex: 1,
    backgroundColor: theme.ui.bg.card,
  },
  world: {
    position: 'absolute',
    left: 0,
    top: 0,
    backgroundColor: theme.ui.bg.card,
  },
  staticLayer: {
    ...StyleSheet.absoluteFillObject,
  },
  tileLayer: {
    ...StyleSheet.absoluteFillObject,
  },
  labelLayer: {
    ...StyleSheet.absoluteFillObject,
  },
  playerMarkerLayer: {
    position: 'absolute',
    width: PLAYER_MARKER_SIZE,
    height: PLAYER_MARKER_SIZE,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 3,
  },
  tile: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'visible',
  },
  selectedGlow: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: alpha(theme.ui.action, 0.52),
    shadowColor: theme.ui.action,
    shadowOpacity: 0.34,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 0 },
    elevation: 5,
  },
  tileTag: {
    ...theme.typography.caption,
    fontSize: 7,
    lineHeight: 8,
    letterSpacing: 0.4,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  tileHint: {
    marginTop: 1,
    ...theme.typography.caption,
    fontSize: 6,
    lineHeight: 7,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '700',
  },
  zoneLabel: {
    position: 'absolute',
    ...theme.typography.caption,
    fontSize: 10,
    lineHeight: 12,
    fontWeight: '800',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
  },
  nodeLabel: {
    position: 'absolute',
    ...theme.typography.caption,
    fontSize: 7,
    lineHeight: 8,
    color: theme.ui.text.onDarkMuted,
    letterSpacing: 0.4,
  },
  playerMarkerPulse: {
    position: 'absolute',
    width: PLAYER_MARKER_PULSE_SIZE,
    height: PLAYER_MARKER_PULSE_SIZE,
    borderRadius: PLAYER_MARKER_PULSE_SIZE / 2,
    backgroundColor: alpha(theme.ui.action, 0.24),
  },
  playerMarkerCore: {
    width: PLAYER_MARKER_SIZE,
    height: PLAYER_MARKER_SIZE,
    borderRadius: PLAYER_MARKER_SIZE / 2,
    backgroundColor: theme.ui.action,
    borderWidth: 2,
    borderColor: theme.ui.bg.sheet,
    shadowColor: theme.ui.action,
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 5,
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
    backgroundColor: alpha(theme.ui.bg.card, 0.94),
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: alpha(theme.ui.border, 0.92),
    ...theme.shadow.md,
  },
  controlButtonWide: {
    minWidth: 72,
    height: 36,
    paddingHorizontal: 12,
    borderRadius: 14,
    backgroundColor: alpha(theme.ui.bg.card, 0.94),
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: alpha(theme.ui.border, 0.92),
    ...theme.shadow.md,
  },
  controlLabel: {
    fontSize: 22,
    lineHeight: 24,
    fontWeight: '700',
    color: theme.ui.text.onDark,
  },
  controlLabelWide: {
    ...theme.typography.caption,
    fontWeight: '800',
    color: theme.ui.text.onDark,
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  locateButton: {
    position: 'absolute',
    right: 16,
    bottom: 16,
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: theme.ui.action,
    borderWidth: 2,
    borderColor: alpha(theme.ui.action, 0.25),
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: theme.ui.action,
    shadowOpacity: 0.22,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 7,
  },
  locateButtonPressed: {
    opacity: 0.82,
  },
  locateButtonDisabled: {
    opacity: 0.45,
  },
});

const GameMap = memo(GameMapComponent);

export default GameMap;

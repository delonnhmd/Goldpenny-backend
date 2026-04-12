import React, { useEffect, useRef } from 'react';
import { Animated, LayoutChangeEvent, StyleSheet, Text, View } from 'react-native';

import PlayerAvatar, { PlayerState } from './PlayerAvatar';
import OpportunityIndicator, { OpportunityType } from './OpportunityIndicator';

export interface MapNode {
  key: string;
  label: string;
  region: 'Suburban' | 'Downtown' | string;
  node_type: string;
  opportunity_tier: string;
  is_current_location: boolean;
}

export interface MapOpportunity {
  key: string;
  type: OpportunityType;
  label: string;
  x: number;
  y: number;
}

interface GameMapProps {
  nodes: MapNode[];
  opportunities: MapOpportunity[];
  playerState: PlayerState;
  currentLocationKey: string;
  stressLevel: number;
  onMapLayout?: (size: { width: number; height: number }) => void;
  mapSize: { width: number; height: number };
}

const PIN_LAYOUT: Record<string, { x: number; y: number }> = {
  home: { x: 18, y: 72 },
  grocery: { x: 24, y: 30 },
  rideshare_hotspot_suburban: { x: 32, y: 52 },
  work: { x: 72, y: 65 },
  rideshare_hotspot_downtown: { x: 78, y: 28 },
  business_spot: { x: 60, y: 48 },
};

const NODE_ICONS: Record<string, string> = {
  home: '\u{1F3E0}',
  work: '\u{1F3E2}',
  grocery: '\u{1F6D2}',
  rideshare_hotspot: '\u{1F697}',
  business: '\u{1F4BC}',
};

function iconForNode(nodeType: string): string {
  return NODE_ICONS[nodeType] || '\u{1F4CD}';
}

export default function GameMap({
  nodes,
  opportunities,
  playerState,
  currentLocationKey,
  stressLevel,
  onMapLayout,
  mapSize,
}: GameMapProps) {
  const handleLayout = (event: LayoutChangeEvent) => {
    const w = Math.round(event.nativeEvent.layout.width);
    const h = Math.round(event.nativeEvent.layout.height);
    if (w > 0 && h > 0) onMapLayout?.({ width: w, height: h });
  };

  const playerPos = PIN_LAYOUT[currentLocationKey] || PIN_LAYOUT.home;

  return (
    <View style={styles.mapContainer} onLayout={handleLayout}>
      {/* Background regions */}
      <View style={styles.suburbanRegion}>
        <Text style={styles.regionLabel}>Suburban</Text>
        {/* Houses */}
        <Text style={styles.sceneryIcon}>{'\u{1F3E1}'}</Text>
        <Text style={[styles.sceneryIcon, { top: '55%', left: '60%' }]}>{'\u{1F3E1}'}</Text>
        <Text style={[styles.sceneryIcon, { top: '75%', left: '25%' }]}>{'\u{1F333}'}</Text>
        <Text style={[styles.sceneryIcon, { top: '35%', left: '70%' }]}>{'\u{1F333}'}</Text>
      </View>
      <View style={styles.downtownRegion}>
        <Text style={styles.regionLabelDT}>Downtown</Text>
        {/* Buildings */}
        <Text style={[styles.sceneryIcon, { top: '20%', left: '55%' }]}>{'\u{1F3E2}'}</Text>
        <Text style={[styles.sceneryIcon, { top: '45%', left: '30%' }]}>{'\u{1F3EC}'}</Text>
        <Text style={[styles.sceneryIcon, { top: '70%', left: '65%' }]}>{'\u{1F3E8}'}</Text>
        <Text style={[styles.sceneryIcon, { top: '15%', left: '20%' }]}>{'\u{1F306}'}</Text>
      </View>

      {/* Roads */}
      <View style={styles.roadHorizontal} />
      <View style={styles.roadVertical} />
      <View style={styles.roadDiagonal} />

      {/* Location pins */}
      {nodes.map((node) => {
        const pos = PIN_LAYOUT[node.key];
        if (!pos) return null;
        const isCurrent = node.key === currentLocationKey;
        return (
          <View key={node.key} style={[styles.pinWrap, { left: `${pos.x}%`, top: `${pos.y}%` }]}>
            <View style={[styles.pinDot, isCurrent && styles.pinDotCurrent]}>
              <Text style={styles.pinIcon}>{iconForNode(node.node_type)}</Text>
            </View>
            <Text style={[styles.pinLabel, isCurrent && styles.pinLabelCurrent]}>{node.label}</Text>
          </View>
        );
      })}

      {/* Opportunity indicators */}
      {opportunities.slice(0, 4).map((opp) => (
        <OpportunityIndicator
          key={opp.key}
          type={opp.type}
          label={opp.label}
          x={opp.x}
          y={opp.y}
        />
      ))}

      {/* Player avatar */}
      <PlayerAvatar
        state={playerState}
        x={playerPos.x}
        y={playerPos.y}
        stressLevel={stressLevel}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  mapContainer: {
    flex: 1,
    borderRadius: 20,
    overflow: 'hidden',
    backgroundColor: '#e8f0e8',
    position: 'relative',
  },
  suburbanRegion: {
    position: 'absolute',
    left: 0,
    top: 0,
    width: '48%',
    height: '100%',
    backgroundColor: '#dcedcc',
    borderRightWidth: 0,
  },
  downtownRegion: {
    position: 'absolute',
    right: 0,
    top: 0,
    width: '52%',
    height: '100%',
    backgroundColor: '#1e293b',
  },
  regionLabel: {
    position: 'absolute',
    top: 8,
    left: 10,
    fontSize: 10,
    fontWeight: '800',
    color: '#3f6212',
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    opacity: 0.7,
  },
  regionLabelDT: {
    position: 'absolute',
    top: 8,
    right: 10,
    fontSize: 10,
    fontWeight: '800',
    color: 'rgba(255, 255, 255, 0.5)',
    textTransform: 'uppercase',
    letterSpacing: 1.2,
  },
  sceneryIcon: {
    position: 'absolute',
    fontSize: 18,
    opacity: 0.25,
    top: '40%',
    left: '30%',
  },
  // Roads
  roadHorizontal: {
    position: 'absolute',
    left: '5%',
    right: '5%',
    top: '50%',
    height: 3,
    backgroundColor: 'rgba(148, 163, 184, 0.35)',
    borderRadius: 2,
  },
  roadVertical: {
    position: 'absolute',
    left: '48%',
    top: '10%',
    bottom: '10%',
    width: 3,
    backgroundColor: 'rgba(148, 163, 184, 0.35)',
    borderRadius: 2,
  },
  roadDiagonal: {
    position: 'absolute',
    left: '20%',
    top: '60%',
    width: '30%',
    height: 2,
    backgroundColor: 'rgba(148, 163, 184, 0.25)',
    borderRadius: 2,
    transform: [{ rotate: '-25deg' }],
  },
  // Pins
  pinWrap: {
    position: 'absolute',
    alignItems: 'center',
    marginLeft: -20,
    marginTop: -20,
    width: 60,
  },
  pinDot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(255, 255, 255, 0.85)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.9)',
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 3,
  },
  pinDotCurrent: {
    borderColor: '#3B82F6',
    backgroundColor: '#EFF6FF',
    shadowColor: '#3B82F6',
    shadowOpacity: 0.3,
  },
  pinIcon: {
    fontSize: 16,
  },
  pinLabel: {
    marginTop: 2,
    fontSize: 9,
    fontWeight: '700',
    color: 'rgba(0, 0, 0, 0.6)',
    textAlign: 'center',
  },
  pinLabelCurrent: {
    color: '#1d4ed8',
    fontWeight: '800',
  },
});

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import {
  BottomSlidePanel,
  FloatingActionButtons,
  GameMap,
  MoneyFeedbackLayer,
  PlayerStatusBar,
} from '@/components/gameMap';
import type {
  BriefItem,
  FABAction,
  MapNode,
  MapOpportunity,
  MoneyFeedbackItem,
  OpportunityCard,
} from '@/components/gameMap';
import type { PlayerState } from '@/components/gameMap/PlayerAvatar';
import type { OpportunityType } from '@/components/gameMap/OpportunityIndicator';
import SafeAreaPage from '@/components/layout/SafeAreaPage';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import type { DashboardSignalItem, EconomySignalChip, WorkStateSnapshot } from '@/types/gameplay';

import { useGameplayLoop } from '../context';

const FALLBACK_NODES: MapNode[] = [
  { key: 'home', label: 'Home', region: 'Suburban', node_type: 'home', opportunity_tier: 'moderate', is_current_location: true },
  { key: 'work', label: 'Work', region: 'Downtown', node_type: 'work', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'grocery', label: 'Grocery', region: 'Suburban', node_type: 'grocery', opportunity_tier: 'low', is_current_location: false },
  { key: 'rideshare_hotspot_downtown', label: 'Rideshare Hub', region: 'Downtown', node_type: 'rideshare_hotspot', opportunity_tier: 'high', is_current_location: false },
  { key: 'rideshare_hotspot_suburban', label: 'Pickup Zone', region: 'Suburban', node_type: 'rideshare_hotspot', opportunity_tier: 'moderate', is_current_location: false },
  { key: 'business_spot', label: 'Business', region: 'Downtown', node_type: 'business', opportunity_tier: 'moderate', is_current_location: false },
];

function derivePlayerState(
  workState: WorkStateSnapshot | null,
  stress: number,
): PlayerState {
  if (!workState) return 'idle';
  if (stress >= 80) return 'stressed';
  const shiftActive = Boolean(workState.main_shift_active_flag || workState.is_on_shift);
  const rideshareActive = Boolean(workState.rideshare_state?.status === 'active');
  if (rideshareActive) return 'driving';
  if (shiftActive) return 'working';
  return 'idle';
}

function deriveOpportunityType(signal: DashboardSignalItem | EconomySignalChip): OpportunityType {
  const text = `${signal.key || ''} ${'title' in signal ? signal.title : ''} ${'category' in signal ? signal.category : ''} ${'label' in signal ? signal.label : ''}`.toLowerCase();
  if (text.includes('deliver') || text.includes('transport') || text.includes('truck')) return 'delivery';
  if (text.includes('produce') || text.includes('food') || text.includes('grocery')) return 'produce';
  if (text.includes('stress') || text.includes('pressure') || text.includes('risk')) return 'stress';
  return 'job';
}

const OPPORTUNITY_POSITIONS: Record<OpportunityType, { x: number; y: number }[]> = {
  delivery: [{ x: 65, y: 38 }, { x: 40, y: 62 }],
  produce: [{ x: 28, y: 18 }, { x: 15, y: 45 }],
  job: [{ x: 82, y: 55 }, { x: 55, y: 30 }],
  stress: [{ x: 85, y: 18 }, { x: 70, y: 80 }],
};

export default function MapDashboardScreen() {
  useScreenTimer('map');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();

  const [mapSize, setMapSize] = useState({ width: 0, height: 0 });
  const [moneyPopups, setMoneyPopups] = useState<MoneyFeedbackItem[]>([]);
  const prevCashRef = useRef<number | null>(null);

  // ── Derive state ──────────────────────────────────────────────────────────
  const authState = loop.authoritativeState || loop.dashboard?.authoritative_state || null;
  const workState = (loop.dashboard?.work_state || loop.actionHub?.work_state || null) as WorkStateSnapshot | null;
  const cityMap = workState?.city_map || null;
  const economyOverview = loop.dashboard?.economy_risk_overview || null;

  const playerStateData = authState?.player_state;
  const cash = Number(playerStateData?.cash ?? loop.dashboard?.stats?.cash_xgp ?? 0);
  const stress = Number(playerStateData?.stress ?? loop.dashboard?.stats?.stress ?? 0);
  const health = Number(playerStateData?.health ?? loop.dashboard?.stats?.health ?? 100);
  const dayNumber = Number(authState?.day_number ?? 1);

  // Money change detection
  if (prevCashRef.current !== null && prevCashRef.current !== cash) {
    const diff = cash - prevCashRef.current;
    if (Math.abs(diff) > 0.5) {
      const id = `money_${Date.now()}_${Math.random()}`;
      setTimeout(() => {
        setMoneyPopups((prev) => [...prev.slice(-3), { id, amount: diff }]);
      }, 0);
    }
  }
  prevCashRef.current = cash;

  const handleMoneyComplete = useCallback((id: string) => {
    setMoneyPopups((prev) => prev.filter((p) => p.id !== id));
  }, []);

  // ── Map nodes ─────────────────────────────────────────────────────────────
  const currentLocationKey = String(
    workState?.current_location_key
    || cityMap?.current_location_key
    || 'home',
  );

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

  // ── Player state ──────────────────────────────────────────────────────────
  const playerState = useMemo(
    () => derivePlayerState(workState, stress),
    [workState, stress],
  );

  // ── Opportunities from economy signals ────────────────────────────────────
  const mapOpportunities: MapOpportunity[] = useMemo(() => {
    const dashOps = loop.dashboard?.top_opportunities || [];
    const ecoOps = economyOverview?.opportunity_signals || [];
    const signals: Array<DashboardSignalItem | EconomySignalChip> = [
      ...dashOps,
      ...ecoOps,
    ].slice(0, 4);

    const posUsed: Record<string, number> = {};
    return signals.map((sig, i) => {
      const type = deriveOpportunityType(sig);
      const idx = posUsed[type] || 0;
      posUsed[type] = idx + 1;
      const positions = OPPORTUNITY_POSITIONS[type];
      const pos = positions[idx % positions.length];
      const sigTitle = 'title' in sig ? sig.title : 'label' in sig ? sig.label : '';
      return {
        key: `opp_${sig.key || i}`,
        type,
        label: String(sigTitle).slice(0, 20),
        x: pos.x,
        y: pos.y,
      };
    });
  }, [economyOverview?.opportunity_signals, loop.dashboard?.top_opportunities]);

  // ── FAB Actions ───────────────────────────────────────────────────────────
  const fabActions: FABAction[] = useMemo(() => {
    const isShiftActive = Boolean(workState?.main_shift_active_flag || workState?.is_on_shift);

    return [
      {
        key: 'work',
        icon: '\u{1F4BC}',
        label: 'Work',
        color: '#3A7DFF',
        disabled: isShiftActive,
        onPress: () => onboarding.navigateTo('work'),
      },
      {
        key: 'drive',
        icon: '\u{1F697}',
        label: 'Drive',
        color: '#22C55E',
        onPress: () => {
          void loop.executeAction({
            action_key: 'side_income',
            title: 'Rideshare',
            description: 'Start a rideshare trip.',
            status: 'available',
            blockers: [],
          });
        },
      },
      {
        key: 'business',
        icon: '\u{1F354}',
        label: 'Business',
        color: '#F59E0B',
        onPress: () => onboarding.navigateTo('business'),
      },
      {
        key: 'relax',
        icon: '\u{1F9D8}',
        label: 'Relax',
        color: '#8B5CF6',
        onPress: () => {
          void loop.executeAction({
            action_key: 'rest',
            title: 'Rest & Relax',
            description: 'Take a break to reduce stress.',
            status: 'available',
            blockers: [],
          });
        },
      },
    ];
  }, [loop, onboarding, workState]);

  // ── Brief items ───────────────────────────────────────────────────────────
  const briefItems: BriefItem[] = useMemo(() => {
    const items: BriefItem[] = [];

    const macroSignals = economyOverview?.macro_conditions || [];
    if (macroSignals.length > 0) {
      items.push({
        key: 'economy',
        icon: '\u{1F4C8}',
        title: economyOverview?.summary_line || 'Market Update',
        bullets: macroSignals.slice(0, 3).map((s: EconomySignalChip) =>
          `${s.label || ''}: ${s.value_text || s.level || ''}`,
        ),
      });
    }

    const risks = loop.dashboard?.top_risks || [];
    if (risks.length > 0) {
      items.push({
        key: 'risks',
        icon: '\u{26A0}\u{FE0F}',
        title: 'Watch Out',
        bullets: risks.slice(0, 2).map((r: DashboardSignalItem) => r.title || ''),
      });
    }

    if (items.length === 0) {
      items.push({
        key: 'default',
        icon: '\u{1F4CB}',
        title: 'Ready for Today',
        bullets: ['Check opportunities below', 'Use actions to earn money'],
      });
    }

    return items;
  }, [economyOverview, loop.dashboard?.top_risks]);

  // ── Opportunity cards ─────────────────────────────────────────────────────
  const opportunityCards: OpportunityCard[] = useMemo(() => {
    const signals = loop.dashboard?.top_opportunities || [];
    return signals.slice(0, 3).map((sig: DashboardSignalItem, i: number) => {
      const type = deriveOpportunityType(sig);
      const emoji = type === 'delivery' ? '\u{1F69A}' : type === 'produce' ? '\u{1F34E}' : type === 'stress' ? '\u{1F525}' : '\u{1F4BC}';

      return {
        key: `opp_card_${sig.key || i}`,
        icon: emoji,
        title: sig.title || 'Opportunity',
        subtitle: (sig.description || 'Tap to take action').slice(0, 50),
        bonus: type === 'delivery' ? '+30% income' : undefined,
        actionLabel: type === 'delivery' ? 'Drive Now' : type === 'produce' ? 'Open Business' : 'Take Action',
        onPress: () => {
          if (type === 'delivery') {
            void loop.executeAction({
              action_key: 'side_income',
              title: 'Rideshare',
              description: 'Start driving.',
              status: 'available',
              blockers: [],
            });
          } else if (type === 'produce') {
            onboarding.navigateTo('business');
          } else {
            onboarding.navigateTo('work');
          }
        },
      };
    });
  }, [loop, onboarding]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <SafeAreaPage edges={['top']}>
      <View style={styles.root}>
        {/* Top status bar */}
        <PlayerStatusBar
          cash={cash}
          stress={stress}
          health={health}
          dayNumber={dayNumber}
        />

        {/* Map area (takes ~70% of screen) */}
        <View style={styles.mapArea}>
          <GameMap
            nodes={nodes}
            opportunities={mapOpportunities}
            playerState={playerState}
            currentLocationKey={currentLocationKey}
            stressLevel={stress}
            mapSize={mapSize}
            onMapLayout={setMapSize}
          />

          {/* Floating action buttons overlay */}
          <FloatingActionButtons actions={fabActions} />

          {/* Money feedback overlay */}
          <MoneyFeedbackLayer items={moneyPopups} onItemComplete={handleMoneyComplete} />
        </View>

        {/* Bottom slide panel */}
        <BottomSlidePanel
          briefItems={briefItems}
          opportunities={opportunityCards}
        />
      </View>
    </SafeAreaPage>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  mapArea: {
    flex: 1,
    marginHorizontal: 0,
    marginTop: 4,
    position: 'relative',
    overflow: 'hidden',
  },
});

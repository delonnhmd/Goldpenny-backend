import React, { useMemo } from 'react';
import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import BusinessOperationsCard from '@/components/gameplay/BusinessOperationsCard';
import { theme } from '@/design/theme';
import { formatMoney } from '@/lib/gameplayFormatters';
import { useScreenTimer } from '@/hooks/useScreenTimer';

import { useGameplayLoop } from '../context';
import {
  GameplayStatCard,
  GameplayStickyActionArea,
  GameplaySummaryCard,
  GameplayWarningBanner,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

function canonicalActionKey(actionKey: string): string {
  const raw = String(actionKey || '').toLowerCase().trim();
  if (!raw) return '';
  if (raw === 'operate_business' || (raw.includes('operate') && raw.includes('business'))) return 'operate_business';
  return raw;
}

export default function BusinessScreen() {
  useScreenTimer('business');
  const loop = useGameplayLoop();
  const activeBusiness = useMemo(
    () => {
      const businesses = loop.businesses?.businesses || [];
      return businesses.find((item) => item.is_active) || businesses[0] || null;
    },
    [loop.businesses?.businesses],
  );

  const marginsForActive = useMemo(() => {
    if (!activeBusiness || !loop.economySummary) return null;
    return loop.economySummary.business_margins.items.find(
      (item) => item.business_key === activeBusiness.business_type,
    ) || null;
  }, [activeBusiness, loop.economySummary]);

  const planForActive = useMemo(() => {
    if (!activeBusiness || !loop.businessPlan) return null;
    return loop.businessPlan.items.find((item) => item.business_key === activeBusiness.business_type) || null;
  }, [activeBusiness, loop.businessPlan]);

  const starterOptions = useMemo(
    () => loop.businesses?.starter_options || [
      { business_type: 'fruit_shop', label: 'Fruit Shop', cost_xgp: 500 },
      { business_type: 'food_truck', label: 'Food Truck', cost_xgp: 1200 },
    ],
    [loop.businesses?.starter_options],
  );

  const operatedToday = loop.dailySession.actionsTakenToday.some(
    (entry) => canonicalActionKey(entry.action_key) === 'operate_business' && entry.success,
  );
  const canOperateNow = Boolean(activeBusiness)
    && loop.dailySession.sessionStatus === 'active'
    && !loop.executingAction
    && !operatedToday;
  const latestProfit = loop.businesses?.profit_snapshot.latest_daily_profit_xgp ?? 0;
  const trailingProfit = loop.businesses?.profit_snapshot.trailing_7d_profit_xgp ?? 0;
  const topRisk = marginsForActive?.risk_factors?.[0]
    || 'No business risk flagged.';
  const cashOnHand = loop.dashboard?.stats.cash_xgp ?? 0;

  return (
    <GameplayLoopScaffold
      title="Business"
      subtitle="Revenue, costs, margin, and risk"
      activeNavKey="business"
      footer={(
        <GameplayStickyActionArea
          secondaryLabel="Back To Market"
          onSecondaryPress={() => router.replace(`/gameplay/loop/${loop.playerId}/market`)}
          primaryLabel={canOperateNow ? 'Operate Business' : 'Open Brief'}
          onPrimaryPress={canOperateNow
            ? () => {
              void loop.operateBusiness();
            }
            : () => router.replace(`/gameplay/loop/${loop.playerId}/brief`)}
          primaryDisabled={canOperateNow ? loop.executingAction : false}
          primaryLoading={canOperateNow ? loop.executingAction : false}
        />
      )}
    >
      <GameplaySummaryCard
        eyebrow="Core split"
        title="Revenue, Cost, Margin, Risk"
      >
        <View style={styles.metricRow}>
          <GameplayStatCard
            label="Revenue (latest)"
            value={formatMoney(latestProfit)}
            tone={latestProfit >= 0 ? 'positive' : 'danger'}
            note="Last operating day result"
          />
          <GameplayStatCard
            label="Cost Pressure"
            value={String(marginsForActive?.cost_pressure || 'Unknown')}
            tone={marginsForActive?.cost_pressure === 'high' ? 'danger' : marginsForActive?.cost_pressure === 'moderate' ? 'warning' : 'neutral'}
            note="Input costs under current economy"
          />
          <GameplayStatCard
            label="Margin Outlook"
            value={String(marginsForActive?.margin_outlook || 'Unknown')}
            tone={marginsForActive?.margin_outlook === 'favorable' ? 'positive' : marginsForActive?.margin_outlook === 'pressured' ? 'danger' : 'warning'}
            note="Expected operating quality"
          />
          <GameplayStatCard
            label="7d Profit"
            value={formatMoney(trailingProfit)}
            tone={trailingProfit >= 0 ? 'positive' : 'danger'}
            note="Recent trend under current conditions"
          />
        </View>
      </GameplaySummaryCard>

      {marginsForActive?.margin_outlook === 'pressured' || marginsForActive?.cost_pressure === 'high' ? (
        <GameplayWarningBanner
          title="Cost pressure is high right now"
          message={topRisk}
          tone="danger"
        />
      ) : null}

      {activeBusiness ? (
        <GameplaySummaryCard
          eyebrow="Execution"
          title="Operate Active Business"
          subtitle="Final check before committing today's run."
        >
          <BusinessOperationsCard
            activeRecord={activeBusiness}
            profitSnapshot={loop.businesses?.profit_snapshot || null}
            margins={marginsForActive}
            plan={planForActive}
            operatedToday={operatedToday}
            sessionActive={loop.dailySession.sessionStatus === 'active'}
            isExecuting={loop.executingAction && canonicalActionKey(loop.busyActionKey || '') === 'operate_business'}
            onOperate={() => {
              void loop.operateBusiness();
            }}
          />
        </GameplaySummaryCard>
      ) : (
        <GameplaySummaryCard
          eyebrow="Start Business"
          title="Starter business costs"
          subtitle="Compare the opening cost to your cash before committing."
        >
          <View style={styles.starterList}>
            {starterOptions.map((option) => {
              const need = Math.max(option.cost_xgp - cashOnHand, 0);
              return (
                <View key={String(option.business_type)} style={styles.starterCard}>
                  <Text style={styles.starterTitle}>{option.label}</Text>
                  <Text style={styles.starterLine}>Cost: {formatMoney(option.cost_xgp)}</Text>
                  <Text style={styles.starterLine}>You have: {formatMoney(cashOnHand)}</Text>
                  <Text style={[styles.starterLine, need > 0 ? styles.needText : styles.readyText]}>
                    Need: {formatMoney(need)}
                  </Text>
                </View>
              );
            })}
          </View>
        </GameplaySummaryCard>
      )}
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  metricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  starterList: {
    gap: theme.spacing.sm,
  },
  starterCard: {
    backgroundColor: theme.color.surfaceAlt,
    borderColor: theme.color.border,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    gap: theme.spacing.xs,
    padding: theme.spacing.md,
  },
  starterTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
  },
  starterLine: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  needText: {
    color: theme.color.warning,
    fontWeight: '700',
  },
  readyText: {
    color: theme.color.positive,
    fontWeight: '700',
  },
});

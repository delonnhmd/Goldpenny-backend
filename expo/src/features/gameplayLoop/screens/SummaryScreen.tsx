import React, { useEffect, useRef } from 'react';
import { Animated, BackHandler, StyleSheet, Text, View } from 'react-native';

import EndOfDaySummaryCard from '@/components/gameplay/EndOfDaySummaryCard';
import PrimaryButton from '@/components/ui/PrimaryButton';
import EmptyStateView from '@/components/ui/EmptyStateView';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { formatDelta, formatMoney } from '@/lib/gameplayFormatters';
import { EndOfDaySummaryResponse, TransactionHistoryItem } from '@/types/gameplay';

import { useGameplayLoop } from '../context';
import { toneFromSignedValue } from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

export function SummaryMomentView({
  summary,
  transactions = [],
  missingAfterSettlement = false,
  endingDay = false,
  canAdvanceDay = true,
  onRunSettlement,
  onContinueToTomorrow,
}: {
  summary: EndOfDaySummaryResponse | null;
  transactions?: TransactionHistoryItem[];
  missingAfterSettlement?: boolean;
  endingDay?: boolean;
  canAdvanceDay?: boolean;
  onRunSettlement: () => void;
  onContinueToTomorrow: () => void;
}) {
  const headlineScale = useRef(new Animated.Value(0.96)).current;
  const headlineOpacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(headlineScale, { toValue: 1, duration: 360, useNativeDriver: true }),
      Animated.timing(headlineOpacity, { toValue: 1, duration: 320, useNativeDriver: true }),
    ]).start();
  }, [headlineOpacity, headlineScale, summary?.day_number, summary?.net_change_xgp]);

  if (!summary && missingAfterSettlement) {
    return (
      <View style={styles.screen}>
        <EmptyStateView
          title="Summary temporarily unavailable"
          subtitle="Settlement completed. Continue to tomorrow, then refresh later for full recap data."
        />
        <PrimaryButton
          testID="summary-continue-button"
          label="Continue to Tomorrow"
          onPress={onContinueToTomorrow}
        />
      </View>
    );
  }

  if (!summary) {
    return (
      <View style={styles.screen}>
        <EmptyStateView
          title="No settled summary yet"
          subtitle="Run settlement to generate today's closeout."
        />
        <PrimaryButton
          testID="summary-run-settlement-button"
          label={endingDay ? 'Settling Day...' : 'Run End Of Day Settlement'}
          loading={endingDay}
          disabled={!canAdvanceDay || endingDay}
          onPress={onRunSettlement}
        />
      </View>
    );
  }

  const netTone = toneFromSignedValue(summary.net_change_xgp);
  const tomorrowFocus = summary.guided_watch_tomorrow
    || summary.tomorrow_warnings[0]
    || (summary.net_change_xgp < 0
      ? 'Rebuild cash before taking extra risk.'
      : 'Protect the cash buffer, then choose one clear growth move.');

  return (
    <View style={styles.screen}>
      <Animated.View style={[styles.hero, { opacity: headlineOpacity, transform: [{ scale: headlineScale }] }]}>
        <Text style={styles.kicker}>Day {summary.day_number || summary.as_of_date} closed</Text>
        <Text style={styles.headline}>{formatMoney(summary.net_change_xgp)} net</Text>
        <Text style={styles.subhead}>
          {summary.net_change_xgp >= 0 ? 'Momentum survived today.' : 'Pressure hit today. Tomorrow is a recovery chance.'}
        </Text>
      </Animated.View>

      <View style={styles.moneyGrid}>
        <View style={styles.moneyCell}>
          <Text style={styles.metricLabel}>Earned</Text>
          <Text style={[styles.metricValue, styles.positive]}>{formatMoney(summary.total_earned_xgp)}</Text>
        </View>
        <View style={styles.moneyCell}>
          <Text style={styles.metricLabel}>Spent</Text>
          <Text style={[styles.metricValue, styles.negative]}>{formatMoney(-Math.abs(summary.total_spent_xgp))}</Text>
        </View>
        <View style={[styles.moneyCell, netTone === 'danger' ? styles.netNegative : styles.netPositive]}>
          <Text style={styles.metricLabel}>Net</Text>
          <Text style={[styles.metricValue, netTone === 'danger' ? styles.negative : styles.positive]}>
            {formatMoney(summary.net_change_xgp)}
          </Text>
        </View>
      </View>

      <View style={styles.storyGrid}>
        <View style={styles.storyPanel}>
          <Text style={styles.storyLabel}>Main gain</Text>
          <Text style={styles.storyValue}>{summary.biggest_gain}</Text>
          <View style={[styles.outcomeBar, styles.outcomeGain]} />
        </View>
        <View style={styles.storyPanel}>
          <Text style={styles.storyLabel}>Main drag</Text>
          <Text style={styles.storyValue}>{summary.biggest_loss}</Text>
          <View style={[styles.outcomeBar, styles.outcomeDrag]} />
        </View>
      </View>

      <View style={styles.chipRow}>
        <View style={styles.deltaChip}>
          <Text style={styles.deltaLabel}>Stress</Text>
          <Text style={styles.deltaValue}>{formatDelta(summary.stress_delta)}</Text>
        </View>
        <View style={styles.deltaChip}>
          <Text style={styles.deltaLabel}>Health</Text>
          <Text style={styles.deltaValue}>{formatDelta(summary.health_delta)}</Text>
        </View>
        <View style={styles.deltaChip}>
          <Text style={styles.deltaLabel}>Skill</Text>
          <Text style={styles.deltaValue}>{formatDelta(summary.skill_delta)}</Text>
        </View>
        <View style={styles.deltaChip}>
          <Text style={styles.deltaLabel}>Credit</Text>
          <Text style={styles.deltaValue}>{formatDelta(summary.credit_score_delta, 0)}</Text>
        </View>
      </View>

      {summary.tomorrow_warnings.length > 0 ? (
        <View style={styles.warningPanel}>
          <Text style={styles.panelTitle}>Warnings</Text>
          {summary.tomorrow_warnings.map((warning, index) => (
            <Text key={`warning_${index}`} style={styles.warningText}>{warning}</Text>
          ))}
        </View>
      ) : null}

      <EndOfDaySummaryCard summary={summary} transactions={transactions} />

      <View style={styles.tomorrowPanel}>
        <Text style={styles.panelTitle}>Tomorrow Focus</Text>
        <Text style={styles.tomorrowText}>{tomorrowFocus}</Text>
      </View>

      <PrimaryButton
        testID="summary-continue-button"
        label="Continue to Tomorrow"
        onPress={onContinueToTomorrow}
      />
    </View>
  );
}

export default function SummaryScreen() {
  useScreenTimer('summary');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const summary = loop.endOfDaySummary;
  const missingAfterSettlement = !summary && loop.dailySession.sessionStatus === 'ended';

  useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (summary || missingAfterSettlement) return true;
      return false;
    });
    return () => {
      subscription.remove();
    };
  }, [missingAfterSettlement, summary]);

  return (
    <GameplayLoopScaffold
      title="End Of Day"
      subtitle="Today's closeout and tomorrow setup"
      activeNavKey="summary"
    >
      <SummaryMomentView
        summary={summary}
        transactions={loop.dailyActivity?.transactions || []}
        missingAfterSettlement={missingAfterSettlement}
        endingDay={loop.endingDay}
        canAdvanceDay={loop.dailyProgression.canAdvanceDay}
        onRunSettlement={() => {
          void loop.endCurrentDay();
        }}
        onContinueToTomorrow={() => {
          void (async () => {
            await loop.startNextDay();
            onboarding.navigateTo('life');
          })();
        }}
      />
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  screen: {
    gap: theme.spacing.lg,
  },
  hero: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.card,
    backgroundColor: theme.ui.bg.card,
    padding: theme.spacing.lg,
    gap: theme.spacing.xs,
  },
  kicker: {
    color: theme.ui.info,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  headline: {
    color: theme.ui.text.onDark,
    fontSize: 34,
    fontWeight: '900',
  },
  subhead: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.bodySm,
  },
  moneyGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  moneyCell: {
    flex: 1,
    minWidth: 98,
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  netPositive: {
    borderColor: theme.ui.positive,
  },
  netNegative: {
    borderColor: theme.ui.danger,
  },
  metricLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  metricValue: {
    color: theme.ui.text.onDark,
    fontSize: 18,
    fontWeight: '900',
  },
  positive: {
    color: theme.ui.positive,
  },
  negative: {
    color: theme.ui.danger,
  },
  storyGrid: {
    gap: theme.spacing.sm,
  },
  storyPanel: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  storyLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  storyValue: {
    color: theme.ui.text.onDark,
    ...theme.typography.bodyMd,
    fontWeight: '800',
  },
  outcomeBar: {
    height: 6,
    borderRadius: 999,
  },
  outcomeGain: {
    width: '88%',
    backgroundColor: theme.ui.positive,
  },
  outcomeDrag: {
    width: '64%',
    backgroundColor: theme.ui.danger,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  deltaChip: {
    flexGrow: 1,
    minWidth: 74,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    borderWidth: 1,
    borderColor: theme.ui.border,
    padding: theme.spacing.sm,
  },
  deltaLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  deltaValue: {
    color: theme.ui.text.onDark,
    ...theme.typography.bodySm,
    fontWeight: '800',
  },
  warningPanel: {
    borderWidth: 1,
    borderColor: theme.ui.danger,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  panelTitle: {
    color: theme.ui.text.onDark,
    ...theme.typography.label,
    fontWeight: '900',
  },
  warningText: {
    color: theme.ui.danger,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  tomorrowPanel: {
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  tomorrowText: {
    color: theme.ui.text.onDark,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
});

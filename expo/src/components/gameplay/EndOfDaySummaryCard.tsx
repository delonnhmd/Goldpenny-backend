import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import AnimatedMoneyValue from '@/components/motion/AnimatedMoneyValue';
import FadeInView from '@/components/motion/FadeInView';
import { theme } from '@/design/theme';
import { formatDelta } from '@/lib/gameplayFormatters';
import { EndOfDaySummaryResponse, TransactionHistoryItem } from '@/types/gameplay';

function tomorrowFocus(summary: EndOfDaySummaryResponse): string {
  if (summary.tomorrow_warnings.length > 0) return summary.tomorrow_warnings[0];
  if (summary.net_change_xgp < 0) return 'Tomorrow starts on defense. Rebuild cash before taking extra risk.';
  if (summary.distress_state && String(summary.distress_state).toLowerCase() !== 'stable') {
    return 'Pressure is still active. Use tomorrow to reduce risk before pushing for growth.';
  }
  return 'You have breathing room. Protect the cash buffer first, then choose one clear growth move.';
}

function bucketTotal(transactions: TransactionHistoryItem[], categories: string[]): number {
  const categorySet = new Set(categories.map((entry) => entry.toLowerCase()));
  return transactions
    .filter((entry) => categorySet.has(String(entry.category || '').toLowerCase()))
    .reduce((sum, entry) => sum + Number(entry.amount || 0), 0);
}

function normalizeExpenseTotal(value: number): number {
  if (value === 0) return 0;
  return -Math.abs(value);
}

type SettlementRow = {
  key: string;
  label: string;
  amount: number;
};

export default function EndOfDaySummaryCard({
  summary,
  transactions = [],
}: {
  summary: EndOfDaySummaryResponse;
  transactions?: TransactionHistoryItem[];
}) {
  const guidedSummaryActive = Number(summary.guided_day_number || 0) >= 1 && Number(summary.guided_day_number || 0) <= 3;
  const netTone = summary.net_change_xgp >= 0 ? '#166534' : '#b91c1c';

  const settlementRows = useMemo<SettlementRow[]>(() => {
    const salary = bucketTotal(transactions, ['salary']);
    const rideShare = bucketTotal(transactions, ['ride_share', 'rideshare']);
    const food = normalizeExpenseTotal(bucketTotal(transactions, ['food']));
    const gas = normalizeExpenseTotal(bucketTotal(transactions, ['gas']));
    const hasBreakdown = transactions.length > 0;
    if (!hasBreakdown) {
      return [
        { key: 'earned', label: 'Earned', amount: summary.total_earned_xgp },
        { key: 'spent', label: 'Spent', amount: -Math.abs(summary.total_spent_xgp) },
        { key: 'net', label: 'Net', amount: summary.net_change_xgp },
      ];
    }
    return [
      { key: 'salary', label: 'Salary', amount: salary },
      { key: 'rideshare', label: 'Rideshare', amount: rideShare },
      { key: 'food', label: 'Food', amount: food },
      { key: 'gas', label: 'Gas', amount: gas },
      { key: 'net', label: 'Net', amount: summary.net_change_xgp },
    ];
  }, [summary.net_change_xgp, summary.total_earned_xgp, summary.total_spent_xgp, transactions]);

  const dayKey = `${summary.player_id}_${summary.day_number || summary.as_of_date}`;

  return (
    <View style={styles.card}>
      <FadeInView delay={0} slide={10}>
        <View style={styles.headerBlock}>
          <Text style={styles.kicker}>Day closed</Text>
          <Text style={styles.heading}>End of Day Summary</Text>
        </View>
      </FadeInView>

      <View style={styles.grid}>
        <FadeInView delay={80} slide={10} key={`${dayKey}_earned`}>
          <View style={styles.metricCard}>
            <Text style={styles.metricLabel}>Earned</Text>
            <AnimatedMoneyValue
              value={summary.total_earned_xgp}
              tone="positive"
              animateOnMountFrom={0}
              durationMs={720}
              threshold={0.01}
              style={styles.metricValue}
            />
          </View>
        </FadeInView>
        <FadeInView delay={160} slide={10} key={`${dayKey}_spent`}>
          <View style={styles.metricCard}>
            <Text style={styles.metricLabel}>Spent</Text>
            <AnimatedMoneyValue
              value={-Math.abs(summary.total_spent_xgp)}
              tone="danger"
              animateOnMountFrom={0}
              durationMs={720}
              threshold={0.01}
              showSign
              style={[styles.metricValue, { color: '#b91c1c' }]}
            />
          </View>
        </FadeInView>
        <FadeInView delay={240} slide={10} key={`${dayKey}_net`}>
          <View style={[styles.metricCard, summary.net_change_xgp >= 0 ? styles.metricPositive : styles.metricNegative]}>
            <Text style={styles.metricLabel}>Net</Text>
            <AnimatedMoneyValue
              value={summary.net_change_xgp}
              tone={summary.net_change_xgp >= 0 ? 'positive' : 'danger'}
              animateOnMountFrom={0}
              durationMs={760}
              threshold={0.01}
              showSign
              style={[styles.metricValue, { color: netTone }]}
            />
          </View>
        </FadeInView>
      </View>

      <View style={[styles.settlementBox, summary.net_change_xgp >= 0 ? styles.settlementPositive : styles.settlementNegative]}>
        <Text style={styles.settlementTitle}>Settlement Breakdown</Text>
        {settlementRows.map((entry, index) => (
          <FadeInView key={`${dayKey}_settle_${entry.key}`} delay={320 + (index * 220)} slide={12}>
            <View style={styles.settlementRow}>
              <Text style={styles.settlementLabel}>{entry.label}</Text>
              <AnimatedMoneyValue
                value={entry.amount}
                tone={entry.amount > 0 ? 'positive' : entry.amount < 0 ? 'danger' : 'neutral'}
                animateOnMountFrom={0}
                durationMs={680}
                threshold={0.01}
                showSign
                style={styles.settlementAmount}
              />
            </View>
          </FadeInView>
        ))}
      </View>

      <FadeInView delay={380 + (settlementRows.length * 220)} slide={10}>
        <View style={styles.storyBox}>
          <Text style={styles.storyTitle}>What mattered most</Text>
          <Text style={styles.storyHeadline} numberOfLines={2}>{summary.biggest_gain}</Text>
          <Text style={styles.storyText} numberOfLines={2}>Main drag: {summary.biggest_loss}</Text>
        </View>
      </FadeInView>

      <FadeInView delay={460 + (settlementRows.length * 220)} slide={10}>
        <View style={styles.deltaRow}>
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
      </FadeInView>

      <Text style={styles.copy}>Distress state: {summary.distress_state}</Text>

      {guidedSummaryActive ? (
        <View style={styles.lessonBox}>
          <Text style={styles.lessonTitle}>{summary.guided_learning_title || `Day ${summary.guided_day_number} lesson`}</Text>
          {summary.guided_earned_summary ? <Text style={styles.lessonText}>{summary.guided_earned_summary}</Text> : null}
          {summary.guided_spent_summary ? <Text style={styles.lessonText}>{summary.guided_spent_summary}</Text> : null}
          {summary.guided_change_summary ? <Text style={styles.lessonText}>{summary.guided_change_summary}</Text> : null}
        </View>
      ) : null}

      {summary.tomorrow_warnings.length > 0 ? (
        <View style={styles.warningBox}>
          <Text style={styles.warningTitle}>Watch tomorrow</Text>
          {summary.tomorrow_warnings.slice(0, 2).map((item, index) => (
            <Text key={`tomorrow_${index}`} style={styles.warningText}>
              - {item}
            </Text>
          ))}
        </View>
      ) : null}

      <View style={styles.focusBox}>
        <Text style={styles.focusTitle}>Tomorrow Focus</Text>
        <Text style={styles.focusText}>{summary.guided_watch_tomorrow || tomorrowFocus(summary)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: '#dbe4ef',
    borderRadius: theme.radius.xl,
    backgroundColor: '#ffffff',
    padding: theme.spacing.lg,
    gap: theme.spacing.md,
  },
  headerBlock: {
    gap: theme.spacing.xxs,
  },
  kicker: {
    color: theme.color.info,
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '800',
  },
  heading: {
    color: theme.color.textPrimary,
    ...theme.typography.headingLg,
    fontWeight: '800',
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  metricCard: {
    flex: 1,
    minWidth: 120,
    borderWidth: 1,
    borderColor: '#dbe4ef',
    borderRadius: theme.radius.lg,
    backgroundColor: '#f8fafc',
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  metricPositive: {
    borderColor: '#86efac',
    backgroundColor: '#f0fdf4',
  },
  metricNegative: {
    borderColor: '#fecaca',
    backgroundColor: '#fef2f2',
  },
  metricLabel: {
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    ...theme.typography.caption,
    fontWeight: '800',
  },
  metricValue: {
    ...theme.typography.bodyMd,
    fontWeight: '800',
  },
  settlementBox: {
    borderWidth: 1,
    borderRadius: theme.radius.xl,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  settlementPositive: {
    borderColor: '#86efac',
    backgroundColor: '#f0fdf4',
  },
  settlementNegative: {
    borderColor: '#fecaca',
    backgroundColor: '#fef2f2',
  },
  settlementTitle: {
    ...theme.typography.label,
    fontWeight: '800',
    color: theme.color.textPrimary,
  },
  settlementRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#dbe4ef',
    paddingBottom: theme.spacing.xs,
  },
  settlementLabel: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
    fontWeight: '700',
  },
  settlementAmount: {
    ...theme.typography.bodySm,
    fontWeight: '800',
  },
  copy: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  storyBox: {
    borderWidth: 1,
    borderColor: '#dbe4ef',
    borderRadius: theme.radius.xl,
    backgroundColor: '#f8fafc',
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  storyTitle: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  storyHeadline: {
    color: theme.color.textPrimary,
    ...theme.typography.bodyMd,
    fontWeight: '700',
  },
  storyText: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  deltaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  deltaChip: {
    borderRadius: theme.radius.lg,
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#dbe4ef',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    minWidth: 88,
    gap: theme.spacing.xxs,
  },
  deltaLabel: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  deltaValue: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  lessonBox: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: theme.radius.xl,
    backgroundColor: '#eff6ff',
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  lessonTitle: {
    color: '#1d4ed8',
    ...theme.typography.bodySm,
    fontWeight: '800',
  },
  lessonText: {
    color: '#1e3a8a',
    ...theme.typography.bodySm,
  },
  warningBox: {
    borderWidth: 1,
    borderColor: '#fecaca',
    borderRadius: theme.radius.xl,
    backgroundColor: '#fef2f2',
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  warningTitle: {
    color: '#b91c1c',
    ...theme.typography.label,
    fontWeight: '800',
  },
  warningText: {
    color: '#7f1d1d',
    ...theme.typography.bodySm,
  },
  focusBox: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: theme.radius.xl,
    backgroundColor: '#eff6ff',
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  focusTitle: {
    color: '#1e40af',
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  focusText: {
    color: '#1e3a8a',
    ...theme.typography.bodySm,
  },
});

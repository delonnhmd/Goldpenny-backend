import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import HighlightOnChangeView from '@/components/motion/HighlightOnChangeView';
import { theme } from '@/design/theme';
import { creditTone, formatMoney, healthTone, stressTone } from '@/lib/gameplayFormatters';
import { type ExpenseDebtContract } from '@/hooks/useExpenseDebt';
import { type JobIncomeContract } from '@/hooks/useJobIncome';
import { useBreakpoint } from '@/hooks/useBreakpoint';
import { GameplayEconomyState } from '@/types/economy';
import { DashboardStatSnapshot } from '@/types/gameplay';

function MetricTile({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string | null;
  tone?: string;
}) {
  return (
    <HighlightOnChangeView watchValue={`${label}:${value}:${note || ''}`} style={styles.metricTile}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, tone ? { color: tone } : null]} numberOfLines={1}>{value}</Text>
      {note ? <Text style={styles.metricNote} numberOfLines={2}>{note}</Text> : null}
    </HighlightOnChangeView>
  );
}

function DetailPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <HighlightOnChangeView watchValue={`${label}:${value}`} style={styles.detailPill}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={[styles.detailValue, tone ? { color: tone } : null]} numberOfLines={1}>{value}</Text>
    </HighlightOnChangeView>
  );
}

export default function PlayerStatsBar({
  stats,
  economy,
  currentGameDay,
  jobIncome,
  expenseDebt,
}: {
  stats: DashboardStatSnapshot;
  economy?: GameplayEconomyState | null;
  currentGameDay?: number | null;
  jobIncome?: JobIncomeContract | null;
  expenseDebt?: ExpenseDebtContract | null;
}) {
  const { isMobile } = useBreakpoint();
  const cashOnHand = economy?.cashOnHand ?? stats.cash_xgp;
  const debtAmount = economy?.debtAmount ?? stats.debt_xgp;
  const netWorthAmount = economy?.netWorthAmount ?? stats.net_worth_xgp;
  const cashFlowTone =
    economy?.netCashFlow == null
      ? theme.color.textSecondary
      : economy.netCashFlow < 0
        ? '#b91c1c'
        : economy.netCashFlow > 0
          ? '#166534'
          : theme.color.textSecondary;
  const debtTone = debtAmount > 0 ? '#b91c1c' : '#166534';
  const pressureTone = economy?.debtPressure === 'critical'
    ? '#b91c1c'
    : economy?.debtPressure === 'high'
      ? '#b45309'
      : theme.color.textSecondary;
  const pressureLabel = economy
    ? economy.debtPressure.charAt(0).toUpperCase() + economy.debtPressure.slice(1)
    : 'Stable';
  const netFlowValue = economy ? economy.cashFlowLabel : 'Unavailable';
  const netFlowNote = expenseDebt?.expenseAmount != null && jobIncome?.incomeAmount != null
    ? `${jobIncome.dailyIncomeLabel} income vs ${expenseDebt.expenseLabel} costs`
    : 'Daily cash direction';

  return (
    <View style={styles.container}>
      <View style={styles.primaryGrid}>
        <MetricTile label="Cash" value={formatMoney(cashOnHand)} note="Available to survive or act today" />
        <MetricTile label="Debt" value={formatMoney(debtAmount)} tone={debtTone} note="What is already pulling against you" />
        <MetricTile label="Net Flow" value={netFlowValue} tone={cashFlowTone} note={netFlowNote} />
        <MetricTile label="Pressure" value={pressureLabel} tone={pressureTone} note="How hard current obligations are hitting" />
      </View>

      <View style={styles.secondaryGrid}>
        {currentGameDay != null ? <DetailPill label="Day" value={String(currentGameDay)} /> : null}
        <DetailPill label="Job" value={(jobIncome?.currentJob ?? stats.current_job) || 'Unassigned'} />
        <DetailPill label="Stress" value={`${Math.round(stats.stress)}`} tone={stressTone(stats.stress)} />
        <DetailPill label="Health" value={`${Math.round(stats.health)}`} tone={healthTone(stats.health)} />
        <DetailPill label="Credit" value={`${Math.round(stats.credit_score)}`} tone={creditTone(stats.credit_score)} />
        {!isMobile ? <DetailPill label="Net Worth" value={formatMoney(netWorthAmount)} /> : null}
        {!isMobile && expenseDebt?.expenseAmount != null ? <DetailPill label="Expenses" value={expenseDebt.expenseLabel} tone={theme.color.warning} /> : null}
        {!isMobile ? <DetailPill label="Region" value={stats.region_key || 'Unknown'} /> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: theme.spacing.md,
  },
  primaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  metricTile: {
    minWidth: 138,
    flex: 1,
    borderWidth: 1,
    borderColor: '#dbe4ef',
    borderRadius: theme.radius.xl,
    backgroundColor: '#ffffff',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  metricLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  metricValue: {
    ...theme.typography.headingMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  metricNote: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    lineHeight: 15,
  },
  secondaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  detailPill: {
    borderRadius: theme.radius.lg,
    backgroundColor: '#f8fafc',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    minWidth: 96,
    gap: theme.spacing.xxs,
  },
  detailLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  detailValue: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
});

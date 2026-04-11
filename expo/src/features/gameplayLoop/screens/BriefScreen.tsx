import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import DailyBriefCard from '@/components/gameplay/DailyBriefCard';
import EndOfDaySummaryCard from '@/components/gameplay/EndOfDaySummaryCard';
import AnimatedMoneyValue from '@/components/motion/AnimatedMoneyValue';
import SlideFadeInOnChange from '@/components/motion/SlideFadeInOnChange';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { formatDelta, formatMoney } from '@/lib/gameplayFormatters';

import { useGameplayLoop } from '../context';
import {
  GameplayCompactMetricRows,
  GameplayStickyActionArea,
  GameplaySummaryCard,
  GameplayTrendChip,
  GameplayWarningBanner,
  toneFromSignedValue,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

export default function BriefScreen() {
  useScreenTimer('brief');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const guidedBriefActive = onboarding.isActive && onboarding.currentStep?.route === 'brief';
  const netFlow = loop.economyState.netCashFlow ?? 0;

  const summary = loop.endOfDaySummary;
  const hasSummary = Boolean(summary);
  const sessionEnded = loop.dailySession.sessionStatus === 'ended';
  const summaryMissingAfterSettlement = !hasSummary && sessionEnded;
  const netTone = toneFromSignedValue(summary?.net_change_xgp ?? 0);

  const dailyActivity = loop.dailyActivity;
  const transactions = dailyActivity?.transactions ?? [];
  const workState = loop.dashboard?.work_state ?? loop.actionHub?.work_state ?? null;
  const salaryEarned = workState?.salary_earned_today ?? 0;
  const salaryEarnedYesterday = workState?.salary_earned_yesterday ?? 0;
  const shiftWindow = workState?.scheduled_shift_window_label ?? 'Scheduled shift';
  const weekend = Boolean(workState?.is_weekend);
  const noShiftScheduled = Boolean(workState?.no_shift_scheduled);
  const workedToday = Boolean(workState?.did_work_today) || salaryEarned > 0;
  const missedToday = Boolean(workState?.missed_shift_today);
  const dayLabel = workState?.current_game_day ?? dailyActivity?.day ?? 1;
  const payModelLabel = String(workState?.pay_model_label || 'Paid daily after shift completion');
  const missedShiftHealthDelta = workState?.missed_shift_health_delta ?? -5;
  const missedShiftStressDelta = workState?.missed_shift_stress_delta ?? 6;
  const salaryPaymentStatus = String(workState?.salary_payment_status || '').toLowerCase();
  const salaryStatusLabel = String(workState?.salary_status_label || 'No salary posted').replace(/Â·/g, '-');
  const salaryStatusMessage = String(workState?.salary_status_message || 'No salary posted yet.').replace(/Â·/g, '-');
  const lastSalaryPosted = workState?.last_salary_posted || null;

  const primaryLabel = hasSummary || summaryMissingAfterSettlement
    ? 'Start Next Day'
    : loop.endingDay
      ? 'Settling Day...'
      : sessionEnded
        ? 'Run Settlement'
        : 'Go To Dashboard';

  const onPrimaryPress = hasSummary || summaryMissingAfterSettlement
    ? () => void loop.startNextDay()
    : sessionEnded
      ? () => void loop.endCurrentDay()
      : () => onboarding.navigateTo('dashboard');

  // STEP 93G — never render the same label on both primary and secondary.
  // When primary itself is "Go To Dashboard" we drop the secondary entirely.
  const primaryIsDashboardNav = primaryLabel === 'Go To Dashboard';
  const showSecondary = !sessionEnded && !primaryIsDashboardNav;

  return (
    <GameplayLoopScaffold
      title="Brief"
      subtitle="Day overview and settlement"
      activeNavKey="brief"
      footer={guidedBriefActive ? null : (
        <GameplayStickyActionArea
          secondaryLabel={showSecondary ? 'Go To Dashboard' : undefined}
          onSecondaryPress={showSecondary ? () => onboarding.navigateTo('dashboard') : undefined}
          primaryLabel={primaryLabel}
          onPrimaryPress={onPrimaryPress}
          primaryLoading={!hasSummary && !summaryMissingAfterSettlement && loop.endingDay}
          primaryDisabled={
            !hasSummary
            && !summaryMissingAfterSettlement
            && sessionEnded
            && (!loop.dailyProgression.canAdvanceDay || loop.endingDay)
          }
        />
      )}
    >
      {loop.dashboard ? (
        <OnboardingHighlight target="brief-daily-economy">
          <SlideFadeInOnChange
            watchValue={`brief_headline_${workState?.current_game_day || dayLabel}_${loop.dashboard.headline || ''}`}
            delayMs={0}
          >
            <DailyBriefCard
              dashboard={loop.dashboard}
              dayKey={workState?.current_game_day || dailyActivity?.day || 1}
            />
          </SlideFadeInOnChange>
        </OnboardingHighlight>
      ) : null}

      <SlideFadeInOnChange
        watchValue={`brief_activity_${workState?.current_game_day || dailyActivity?.day || 1}_${transactions.length}_${Math.round((dailyActivity?.net ?? netFlow) * 100)}`}
        delayMs={80}
      >
      <GameplaySummaryCard eyebrow="Today" title="Daily Activity">
        <GameplayCompactMetricRows
          items={[
            {
              label: 'Income',
              value: formatMoney(dailyActivity?.total_income ?? 0),
              tone: 'positive',
              valueNode: (
                <AnimatedMoneyValue
                  value={dailyActivity?.total_income ?? 0}
                  tone="positive"
                  threshold={0.1}
                  durationMs={700}
                />
              ),
            },
            {
              label: 'Expense',
              value: formatMoney(dailyActivity?.total_expense ?? 0),
              tone: 'danger',
              valueNode: (
                <AnimatedMoneyValue
                  value={dailyActivity?.total_expense ?? 0}
                  tone="danger"
                  threshold={0.1}
                  durationMs={700}
                  invertDeltaTone
                />
              ),
            },
            {
              label: 'Net',
              value: `${(dailyActivity?.net ?? 0) > 0 ? '+' : ''}${formatMoney(dailyActivity?.net ?? netFlow)}`,
              tone: toneFromSignedValue(dailyActivity?.net ?? netFlow),
              valueNode: (
                <AnimatedMoneyValue
                  value={dailyActivity?.net ?? netFlow}
                  tone={toneFromSignedValue(dailyActivity?.net ?? netFlow) === 'positive' ? 'positive' : toneFromSignedValue(dailyActivity?.net ?? netFlow) === 'danger' ? 'danger' : 'neutral'}
                  threshold={0.1}
                  durationMs={750}
                  showSign
                />
              ),
            },
          ]}
        />
        {transactions.length > 0 ? (
          <View style={styles.transactionList}>
            {transactions.map((entry) => (
              <View key={entry.id} style={styles.transactionRow}>
                <View style={styles.transactionCopy}>
                  <Text style={styles.transactionTitle}>{entry.description}</Text>
                  <Text style={styles.transactionMeta}>{entry.category.replace(/_/g, ' ')}</Text>
                </View>
                <Text style={[styles.transactionAmount, entry.amount >= 0 ? styles.positiveText : styles.negativeText]}>
                  {entry.amount > 0 ? '+' : ''}
                  {formatMoney(entry.amount)}
                </Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.txPlaceholder}>
            No transactions recorded yet for Day {dailyActivity?.day ?? workState?.current_game_day ?? 1}.
          </Text>
        )}
      </GameplaySummaryCard>
      </SlideFadeInOnChange>

      <SlideFadeInOnChange
        watchValue={`brief_work_${workState?.current_game_day || 1}_${workedToday ? 'worked' : missedToday ? 'missed' : weekend ? 'weekend' : 'pending'}_${Math.round(salaryEarned * 100)}`}
        delayMs={120}
      >
      <GameplaySummaryCard eyebrow="Work" title="Work Status">
        {workedToday ? (
          <GameplayCompactMetricRows
            items={[
              {
                label: 'Status',
                value: salaryStatusLabel,
                tone: salaryPaymentStatus === 'failed' ? 'danger' : salaryPaymentStatus === 'pending' ? 'warning' : 'positive',
              },
              { label: 'Window', value: shiftWindow, tone: 'neutral' },
              {
                label: 'Earned',
                value: salaryEarned > 0 ? `+${formatMoney(salaryEarned)}` : 'Pending',
                tone: salaryEarned > 0 ? 'positive' : salaryPaymentStatus === 'failed' ? 'danger' : 'warning',
              },
            ]}
          />
        ) : weekend ? (
          <GameplayCompactMetricRows
            items={[
              { label: 'Status', value: 'Weekend', tone: 'positive' },
              { label: 'Shift', value: 'No required shift', tone: 'neutral' },
              { label: 'Ride Share', value: 'Available all day', tone: 'positive' },
            ]}
          />
        ) : missedToday ? (
          <GameplayCompactMetricRows
            items={[
              { label: 'Status', value: 'Missed shift', tone: 'danger' },
              { label: 'Salary', value: 'No salary earned', tone: 'warning' },
              {
                label: 'Health / Stress',
                value: `${formatDelta(missedShiftHealthDelta)} / ${formatDelta(missedShiftStressDelta)}`,
                tone: 'danger',
              },
            ]}
          />
        ) : noShiftScheduled ? (
          <GameplayCompactMetricRows
            items={[
              { label: 'Status', value: 'No shift scheduled', tone: 'neutral' },
              {
                label: 'Ride Share',
                value: workState?.rideshare_available ? 'Unlocked' : 'Available when ready',
                tone: 'neutral',
              },
            ]}
          />
        ) : (
          <GameplayCompactMetricRows
            items={[
              { label: 'Status', value: 'Weekday shift pending', tone: 'warning' },
              { label: 'Window', value: shiftWindow, tone: 'neutral' },
              {
                label: 'Ride Share',
                value: workState?.rideshare_available ? 'Available now' : `Available after ${workState?.rideshare_unlock_time_label ?? 'shift end'}`,
                tone: 'warning',
              },
            ]}
          />
        )}
        <GameplayCompactMetricRows
          items={[
            { label: 'Pay model', value: payModelLabel, tone: 'info' },
            {
              label: 'Yesterday salary',
              value: salaryEarnedYesterday > 0 ? `+${formatMoney(salaryEarnedYesterday)}` : '--',
              tone: salaryEarnedYesterday > 0 ? 'positive' : 'neutral',
            },
            {
              label: 'Last salary',
              value: lastSalaryPosted ? `+${formatMoney(lastSalaryPosted.final_salary_paid)}` : '--',
              tone: lastSalaryPosted?.transaction_confirmed ? 'positive' : 'neutral',
            },
          ]}
        />
        {missedToday ? (
          <Text style={styles.statusCaption}>
            Missing a weekday shift now shows the lost pay outcome directly and logs the health and stress hit.
          </Text>
        ) : workedToday ? (
          <Text style={styles.statusCaption}>
            {salaryStatusMessage}
          </Text>
        ) : weekend ? (
          <Text style={styles.statusCaption}>
            Weekend rules remove the required main shift and keep ride share open for the full day.
          </Text>
        ) : null}
      </GameplaySummaryCard>
      </SlideFadeInOnChange>

      {sessionEnded ? (
        <OnboardingHighlight target="summary-day-results">
          <SlideFadeInOnChange
            watchValue={`brief_settlement_state_${workState?.current_game_day || 1}_${loop.dailySession.sessionStatus}_${loop.dailySession.actionsTakenToday.length}`}
            delayMs={160}
          >
          <GameplaySummaryCard
            eyebrow="Day closeout"
            title="Settlement Status"
          >
            <View style={styles.chipRow}>
              <GameplayTrendChip
                label="Session"
                value="Ended"
                tone="warning"
              />
              <GameplayTrendChip
                label="Actions"
                value={String(loop.dailySession.actionsTakenToday.length)}
                tone="neutral"
              />
              <GameplayTrendChip
                label="Ending cash"
                value={formatMoney(loop.dashboard?.stats.cash_xgp ?? 0)}
                tone="neutral"
              />
            </View>
          </GameplaySummaryCard>
          </SlideFadeInOnChange>
        </OnboardingHighlight>
      ) : null}

      {summary ? (
        <>
          <GameplaySummaryCard
            eyebrow="Today's result"
            title={summary.net_change_xgp >= 0
              ? 'Nice finish today.'
              : 'Tough day - tomorrow can recover this.'}
          >
            <GameplayCompactMetricRows
              items={[
                { label: 'Net', value: formatMoney(summary.net_change_xgp), tone: netTone },
                { label: 'Earned', value: formatMoney(summary.total_earned_xgp), tone: 'positive' },
                { label: 'Spent', value: formatMoney(summary.total_spent_xgp), tone: 'danger' },
                { label: 'Stress delta', value: formatDelta(summary.stress_delta), tone: summary.stress_delta > 0 ? 'danger' : 'positive' },
                { label: 'Health delta', value: formatDelta(summary.health_delta), tone: summary.health_delta >= 0 ? 'positive' : 'warning' },
              ]}
            />
          </GameplaySummaryCard>
          <EndOfDaySummaryCard summary={summary} />
        </>
      ) : summaryMissingAfterSettlement ? (
        <EmptyStateView
          title="Summary temporarily unavailable"
          subtitle="Settlement completed. Continue to the next day - refresh later for full recap."
        />
      ) : !sessionEnded ? (
        <GameplayWarningBanner
          title="Day still active"
          message="Run End Day from the Dashboard when you are done with your actions."
          tone="info"
        />
      ) : null}
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  transactionList: {
    gap: theme.spacing.sm,
  },
  transactionRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  transactionCopy: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  transactionTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
  },
  transactionMeta: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    textTransform: 'capitalize',
  },
  transactionAmount: {
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  positiveText: {
    color: theme.color.positive,
  },
  negativeText: {
    color: theme.color.danger,
  },
  statusCaption: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
  },
  txPlaceholder: {
    color: theme.color.muted,
    ...theme.typography.caption,
    fontStyle: 'italic',
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
});

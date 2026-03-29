import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import EndOfDaySummaryCard from '@/components/gameplay/EndOfDaySummaryCard';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { formatDelta, formatMoney } from '@/lib/gameplayFormatters';
import { recordInfo } from '@/lib/logger';
import { useScreenTimer } from '@/hooks/useScreenTimer';

import { useGameplayLoop } from '../context';
import {
  GameplayCompactMetricRows,
  GameplayOpportunityCallout,
  GameplayStickyActionArea,
  GameplaySummaryCard,
  GameplayTrendChip,
  GameplayWarningBanner,
  toneFromSignedValue,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

const INTERACTION_DIAGNOSTICS_ENABLED =
  __DEV__
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

export default function SummaryScreen() {
  useScreenTimer('summary');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const guidedSummaryActive = onboarding.isActive && onboarding.currentStep?.route === 'summary';
  const simplified = onboarding.isSimplifiedMode;
  const summary = loop.endOfDaySummary;
  const hasSummary = Boolean(summary);
  const summaryMissingAfterSettlement = !hasSummary && loop.dailySession.sessionStatus === 'ended';
  const netTone = toneFromSignedValue(summary?.net_change_xgp ?? 0);
  const payoffTitle = summary
    ? summary.net_change_xgp >= 0
      ? 'Nice finish today. Protect momentum tomorrow.'
      : 'Tough day. Tomorrow can still recover this.'
    : 'Settle the day to unlock today\'s payoff screen.';
  const winsLine = summary?.biggest_gain || 'No biggest gain recorded yet.';
  const lossLine = summary?.biggest_loss || 'No biggest loss recorded yet.';

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Summary screen gate evaluated.', {
      action: 'summary_screen_gate',
      context: {
        playerId: loop.playerId,
        hasSummary,
        sessionStatus: loop.dailySession.sessionStatus,
        reason: hasSummary
          ? 'settlement_summary_present'
          : loop.dailySession.sessionStatus === 'ended'
            ? 'session_ended_but_summary_missing'
            : 'session_not_ended_yet',
      },
    });
  }, [hasSummary, loop.dailySession.sessionStatus, loop.playerId]);

  return (
    <GameplayLoopScaffold
      title="End Of Day Summary"
      subtitle="Close today, read changes, and set up tomorrow"
      activeNavKey="summary"
      footer={(
        <GameplayStickyActionArea
          summary={hasSummary
            ? `Tomorrow setup: ${summary?.guided_watch_tomorrow || summary?.tomorrow_warnings?.[0] || 'Start with one low-risk income action.'}`
            : summaryMissingAfterSettlement
              ? 'Settlement completed but summary payload is unavailable. You can continue to the next day.'
              : `Session ${loop.dailySession.sessionStatus}. Run settlement to generate today's recap.`}
          secondaryLabel={guidedSummaryActive ? undefined : hasSummary || summaryMissingAfterSettlement ? 'Open Dashboard' : 'Go To Work'}
          onSecondaryPress={guidedSummaryActive
            ? undefined
            : () => {
              onboarding.navigateTo(hasSummary || summaryMissingAfterSettlement ? 'dashboard' : 'work');
            }}
          primaryLabel={hasSummary || summaryMissingAfterSettlement ? 'Start Next Day' : loop.endingDay ? 'Settling Day...' : 'Run End Of Day Settlement'}
          onPrimaryPress={hasSummary || summaryMissingAfterSettlement
            ? () => {
              void loop.startNextDay();
            }
            : () => {
              void loop.endCurrentDay();
            }}
          primaryLoading={!hasSummary && !summaryMissingAfterSettlement && loop.endingDay}
          primaryDisabled={!hasSummary && !summaryMissingAfterSettlement && (!loop.dailyProgression.canAdvanceDay || loop.endingDay)}
        />
      )}
    >
      <OnboardingHighlight target="summary-day-results">
        <GameplaySummaryCard
          eyebrow="Settlement controls"
          title="Closeout Status"
          subtitle="Run settlement after your actions are done for the day."
        >
          <View style={styles.chipRow}>
            <GameplayTrendChip
              label="Session"
              value={loop.dailySession.sessionStatus === 'active' ? 'Active' : 'Ended'}
              tone={loop.dailySession.sessionStatus === 'active' ? 'info' : 'warning'}
            />
            <GameplayTrendChip
              label="Actions"
              value={String(loop.dailySession.actionsTakenToday.length)}
              tone="neutral"
            />
            <GameplayTrendChip
              label="Time left"
              value={`${loop.dailySession.remainingTimeUnits}/${loop.dailySession.totalTimeUnits}`}
              tone={loop.dailySession.remainingTimeUnits <= 2 ? 'warning' : 'info'}
            />
            <GameplayTrendChip
              label="Ending cash"
              value={formatMoney(loop.dashboard?.stats.cash_xgp ?? 0)}
              tone="neutral"
            />
          </View>
        </GameplaySummaryCard>
      </OnboardingHighlight>

      {summary ? (
        <>
          <GameplaySummaryCard
            eyebrow="Emotional payoff"
            title={payoffTitle}
            subtitle="What changed today and what tomorrow needs."
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

          {!simplified ? (
            <GameplayOpportunityCallout
              title="Today Win"
              message={winsLine}
            />
          ) : null}
          {!simplified ? (
            <GameplayWarningBanner
              title="Today Loss"
              message={lossLine}
              tone="warning"
            />
          ) : null}

          <OnboardingHighlight target="summary-day-results">
            <EndOfDaySummaryCard summary={summary} />
          </OnboardingHighlight>
        </>
      ) : summaryMissingAfterSettlement ? (
        <EmptyStateView
          title="Summary temporarily unavailable"
          subtitle="Settlement completed. You can continue to the next day, then refresh later for full recap data."
        />
      ) : (
        <EmptyStateView
          title="No settled summary yet"
          subtitle="Run end-of-day settlement to generate today's recap."
        />
      )}
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
});

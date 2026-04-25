import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import { OnboardingHighlight } from '@/components/onboarding';
import PrimaryButton from '@/components/ui/PrimaryButton';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { BALANCE } from '@/lib/balanceConfig';
import { formatMoney } from '@/lib/gameplayFormatters';
import { recordInfo } from '@/lib/logger';
import { DailyActionItem, JobMarketJobSnapshot } from '@/types/gameplay';

import JobMarketPanel from '../components/JobMarketPanel';
import { useGameplayLoop } from '../context';
import {
  GameplayCompactMetricRows,
  GameplayStatCard,
  GameplayStickyActionArea,
  GameplaySummaryCard,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

const INTERACTION_DIAGNOSTICS_ENABLED =
  __DEV__
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

export default function WorkScreen() {
  useScreenTimer('work');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const guidedWorkActive = onboarding.isActive && onboarding.currentStep?.route === 'work';
  const stats = loop.dashboard?.stats;
  const workState = loop.dashboard?.work_state || loop.actionHub?.work_state || null;
  const jobMarket = workState?.job_market || null;
  const currentJobKey = String(
    jobMarket?.current_job_key
    || workState?.authoritative_current_job_id
    || workState?.active_shift_job_id
    || workState?.scheduled_shift_job_id
    || loop.actionHub?.debug_meta?.current_job_key
    || loop.dashboard?.stats?.current_job
    || '',
  ).trim();
  const hasMainJobSelected = Boolean(
    jobMarket?.has_main_job
    ?? loop.actionHub?.debug_meta?.has_starter_job_selected
    ?? currentJobKey,
  );
  const firstSessionFlag = Boolean(
    loop.dashboard?.debug_meta?.new_player_first_session
    ?? loop.actionHub?.debug_meta?.new_player_first_session
    ?? false,
  );
  const showJobMarket = Boolean(
    (jobMarket?.jobs && jobMarket.jobs.length > 0)
    || firstSessionFlag
    || !hasMainJobSelected,
  );

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Work job market visibility evaluated.', {
      action: 'job_selection_visibility',
      context: {
        playerId: loop.playerId,
        firstSessionFlag,
        showJobMarket,
        jobMarketOptionsCount: jobMarket?.jobs?.length || 0,
        hasMainJobSelected,
        currentJobKey: currentJobKey || null,
      },
    });
  }, [
    currentJobKey,
    firstSessionFlag,
    hasMainJobSelected,
    jobMarket?.jobs?.length,
    loop.playerId,
    showJobMarket,
  ]);

  const switchToMarketJob = (job: JobMarketJobSnapshot) => {
    const targetJobKey = String(job.job_key || '').trim().toLowerCase();
    if (!targetJobKey) return;
    if (INTERACTION_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayLoop', 'Job market switch requested from work screen.', {
        action: 'work_screen_switch_job_selected',
        context: {
          playerId: loop.playerId,
          targetJobKey,
          currentJobKey: currentJobKey || null,
        },
      });
    }
    const action: DailyActionItem = {
      action_key: 'switch_job',
      title: `Switch to ${job.display_name || targetJobKey.replace(/_/g, ' ')}`,
      description: 'Switch main job from Job Market.',
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'high',
      parameters: {
        new_job_key: targetJobKey,
      },
    };
    void loop.executeAction(action);
  };

  const startMarketTraining = (job: JobMarketJobSnapshot) => {
    const certificationKey = String(job.certification_key || '').trim().toLowerCase();
    if (!certificationKey) return;
    if (INTERACTION_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayLoop', 'Job market training requested from work screen.', {
        action: 'work_screen_start_training_selected',
        context: {
          playerId: loop.playerId,
          certificationKey,
          targetJobKey: String(job.job_key || ''),
        },
      });
    }
    const action: DailyActionItem = {
      action_key: 'start_training',
      title: `Start Training: ${job.certification_name || certificationKey.replace(/_/g, ' ')}`,
      description: 'Begin certification training to unlock this job.',
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'medium',
      parameters: {
        certification_key: certificationKey,
      },
    };
    void loop.executeAction(action);
  };

  const salaryEarnedToday = Number(workState?.salary_earned_today || 0);
  const salaryEarnedYesterday = Number(workState?.salary_earned_yesterday || 0);
  const salaryPaymentStatus = String(workState?.salary_payment_status || '').toLowerCase();
  const salaryStatusLabel = String(workState?.salary_status_label || 'No salary posted').replace(/Ãƒâ€šÃ‚Â·/g, '-');
  const currentJobLabel = String(
    jobMarket?.current_job_display_name
    || workState?.current_job_display_name
    || loop.dashboard?.stats?.current_job_display
    || loop.jobIncome.currentJob
    || 'No job selected',
  ).replace(/_/g, ' ');
  const shiftWindow = workState?.is_weekend
    ? 'Weekend - no required shift'
    : workState?.scheduled_shift_window_label || 'Use the map work node';
  const workStatusTone = salaryPaymentStatus === 'failed'
    ? 'danger'
    : salaryEarnedToday > 0
      ? 'positive'
      : 'warning';

  return (
    <GameplayLoopScaffold
      title="Work"
      subtitle="Turn your time into money"
      activeNavKey="work"
      footer={guidedWorkActive ? null : (
        <GameplayStickyActionArea
          summary={`${loop.dailySession.remainingTimeUnits} time units left today`}
          secondaryLabel="Open Map"
          onSecondaryPress={() => {
            onboarding.navigateTo('map');
          }}
          primaryLabel="Open Portfolio"
          onPrimaryPress={() => {
            onboarding.navigateTo('market');
          }}
          primaryDisabled={false}
        />
      )}
    >
      <OnboardingHighlight target="work-status">
        <GameplaySummaryCard
          eyebrow="Your work status"
          title="Income, Energy & Time"
          subtitle="Track pay, pressure, and job setup here. Start shifts from the map work node."
        >
          <View style={styles.metricRow}>
            <GameplayStatCard
              label="Today's pay"
              value={salaryEarnedToday > 0 ? `+${formatMoney(salaryEarnedToday)}` : loop.jobIncome.dailyIncomeLabel}
              tone={workStatusTone}
              note={currentJobLabel}
            />
            <GameplayStatCard
              label="Stress"
              value={`${Math.round(stats?.stress ?? 0)}`}
              tone={(stats?.stress ?? 0) >= 65 ? 'danger' : 'warning'}
              note="High stress slows recovery and raises mistakes."
            />
            <GameplayStatCard
              label="Health"
              value={`${Math.round(stats?.health ?? 100)}`}
              tone={(stats?.health ?? 100) >= 65 ? 'positive' : 'warning'}
              note="Low health reduces earnings from shifts."
            />
            <GameplayStatCard
              label="Time left"
              value={`${loop.dailySession.remainingTimeUnits}/${loop.dailySession.totalTimeUnits}`}
              tone={loop.dailySession.remainingTimeUnits <= 2 ? 'warning' : 'info'}
              note={`1 unit = ${BALANCE.REALTIME.MINUTES_PER_UNIT} mins. Timed activities now consume units over time.`}
            />
          </View>
          <GameplayCompactMetricRows
            items={[
              { label: 'Shift window', value: shiftWindow, tone: 'neutral' },
              { label: 'Salary status', value: salaryStatusLabel, tone: workStatusTone },
              { label: 'Yesterday salary', value: salaryEarnedYesterday > 0 ? `+${formatMoney(salaryEarnedYesterday)}` : '--', tone: salaryEarnedYesterday > 0 ? 'positive' : 'neutral' },
            ]}
          />
        </GameplaySummaryCard>
      </OnboardingHighlight>

      {showJobMarket ? (
        <JobMarketPanel
          jobMarket={jobMarket}
          executingAction={loop.executingAction}
          busyActionKey={loop.busyActionKey}
          onSwitchJob={switchToMarketJob}
          onStartTraining={startMarketTraining}
          interactionDisabledReason="Use the Job Center on the map to switch jobs or start certifications."
        />
      ) : null}

      <GameplaySummaryCard
        eyebrow="Map Actions"
        title="Job board and shift actions now live on the map"
        subtitle="Use the Job Center for hiring and certifications, then use your work location node to run shifts and shift-focus bonuses."
      >
        <PrimaryButton
          label="Open Map Work Node"
          onPress={() => onboarding.navigateTo('map')}
        />
      </GameplaySummaryCard>
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  metricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
});

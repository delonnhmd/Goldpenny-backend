import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import ActionHubPanel from '@/components/gameplay/ActionHubPanel';
import ActionPreviewModal from '@/components/gameplay/ActionPreviewModal';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { recordInfo } from '@/lib/logger';
import { DailyActionItem, JobMarketJobSnapshot } from '@/types/gameplay';

import JobMarketPanel from '../components/JobMarketPanel';
import { useGameplayLoop } from '../context';
import {
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
  const endDayDisabled = !loop.dailyProgression.canAdvanceDay || loop.endingDay;
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

  return (
    <GameplayLoopScaffold
      title="Work / Job"
      subtitle="Turn your time into money"
      activeNavKey="work"
      footer={guidedWorkActive ? null : (
        <GameplayStickyActionArea
          summary={`${loop.dailySession.remainingTimeUnits} time units left today`}
          secondaryLabel="Open Market"
          onSecondaryPress={() => {
            onboarding.navigateTo('market');
          }}
          primaryLabel={loop.endingDay ? 'Settling Day...' : 'End Day'}
          onPrimaryPress={() => {
            void loop.endCurrentDay();
          }}
          primaryLoading={loop.endingDay}
          primaryDisabled={endDayDisabled}
        />
      )}
    >
      <GameplaySummaryCard
        eyebrow="Your work status"
        title="Income, Energy &amp; Time"
        subtitle="Start a shift to earn money. Each shift uses time and increases stress."
      >
        <View style={styles.metricRow}>
          <GameplayStatCard
            label="Today's pay"
            value={loop.jobIncome.dailyIncomeLabel}
            tone={loop.jobIncome.incomeAmount != null && loop.jobIncome.incomeAmount >= 0 ? 'positive' : 'warning'}
            note={loop.jobIncome.currentJob ? loop.jobIncome.currentJob.replace(/_/g, ' ') : 'No job selected yet'}
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
            note="Each shift uses time units."
          />
        </View>
      </GameplaySummaryCard>

      {showJobMarket ? (
        <JobMarketPanel
          jobMarket={jobMarket}
          executingAction={loop.executingAction}
          busyActionKey={loop.busyActionKey}
          onSwitchJob={switchToMarketJob}
          onStartTraining={startMarketTraining}
        />
      ) : null}

      {loop.actionHub ? (
        <OnboardingHighlight target="work-first-action">
          <ActionHubPanel
            hub={loop.actionHub}
            onExecuteAction={(action: DailyActionItem) => {
              void loop.openActionPreview(action);
            }}
            getExecutionGuard={(action) => loop.dailySession.canExecuteAction(action)}
            remainingTimeUnits={loop.dailySession.remainingTimeUnits}
            totalTimeUnits={loop.dailySession.totalTimeUnits}
            sessionStatus={loop.dailySession.sessionStatus}
            progressRatio={loop.dailySession.progress}
          />
        </OnboardingHighlight>
      ) : (
        <EmptyStateView
          title="No actions loaded"
          subtitle="Refresh to pull the latest action hub."
        />
      )}

      <ActionPreviewModal
        visible={Boolean(loop.selectedPreviewAction)}
        action={loop.selectedPreviewAction}
        preview={loop.actionPreview}
        loading={loop.previewLoading}
        error={loop.previewError}
        onClose={loop.closeActionPreview}
        onExecuteAction={() => {
          void loop.executeSelectedAction();
        }}
        executeDisabled={loop.dailySession.sessionStatus !== 'active'}
        executeGuard={loop.selectedPreviewAction ? loop.dailySession.canExecuteAction(loop.selectedPreviewAction) : undefined}
        executing={loop.executingAction}
      />
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

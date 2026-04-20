import React, { useEffect, useMemo } from 'react';
import { StyleSheet, View } from 'react-native';

import ActionHubPanel from '@/components/gameplay/ActionHubPanel';
import ActionPreviewModal from '@/components/gameplay/ActionPreviewModal';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
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
  const actionHubForDisplay = useMemo(() => {
    if (!loop.actionHub) return null;
    const hiddenKeys = new Set([
      'rest',
      'study',
      'watch_tv',
      'watch_movie',
      'read_book',
      'jogging',
      'eat_meal',
      'skill_training',
      'start_training',
      'work_shift',
      'side_income',
      'operate_business',
      'buy_inventory',
    ]);
    const filterActions = (actions: DailyActionItem[]) =>
      actions.filter((action) => {
        const rawKey = String(action.action_key || '').trim().toLowerCase();
        if (hiddenKeys.has(rawKey)) return false;
        if (
          rawKey.includes('recover')
          || rawKey.includes('watch_')
          || rawKey.includes('jog')
          || rawKey.includes('eat_')
          || rawKey.includes('work')
          || rawKey.includes('shift')
          || rawKey.includes('ride')
          || rawKey.includes('side_income')
          || rawKey.includes('business')
          || rawKey.includes('inventory')
        ) {
          return false;
        }
        return true;
      });
    return {
      ...loop.actionHub,
      recommended_actions: filterActions(loop.actionHub.recommended_actions || []),
      available_actions: filterActions(loop.actionHub.available_actions || []),
      blocked_actions: filterActions(loop.actionHub.blocked_actions || []),
    };
  }, [loop.actionHub]);
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
  const jobProgress = loop.dashboard?.job_progress || null;
  const currentJobLabel = String(
    jobProgress?.position_title
    || stats?.current_job_display
    || loop.jobIncome.currentJob
    || stats?.current_job
    || 'No job selected',
  ).replace(/_/g, ' ');
  const shiftWindow = workState?.testing_mode?.enabled && workState.testing_mode.shift_length_label
    ? `On-demand - ${workState.testing_mode.shift_length_label}`
    : workState?.scheduled_shift_window_label || 'No scheduled shift';
  const payModelLabel = String(workState?.pay_model_label || 'Paid daily after shift completion');
  const salaryToday = Number(workState?.salary_earned_today ?? loop.jobIncome.incomeAmount ?? 0);
  const salaryStatus = String(workState?.salary_status_label || 'No salary posted').replace(/Â·/g, '-');
  const nextSalaryLabel = jobProgress?.estimated_next_level_monthly_salary_xgp
    ? formatMoney(jobProgress.estimated_next_level_monthly_salary_xgp)
    : 'Awaiting level data';
  const jobLevelLabel = jobProgress ? `Lv ${jobProgress.job_level}` : 'Unranked';
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
          secondaryLabel="Open Portfolio"
          onSecondaryPress={() => {
            onboarding.navigateTo('portfolio');
          }}
          primaryLabel="Open Summary"
          onPrimaryPress={() => {
            onboarding.navigateTo('summary');
          }}
          primaryDisabled={false}
        />
      )}
    >
      <OnboardingHighlight target="work-career-overview">
        <GameplaySummaryCard
          eyebrow="Career overview"
          title="Income, shifts, and momentum"
          subtitle="Career stats from the old dashboard now live here."
        >
          <GameplayCompactMetricRows
            items={[
              { label: 'Current job', value: currentJobLabel, tone: currentJobKey ? 'info' : 'warning' },
              { label: 'Shift window', value: shiftWindow, tone: 'info' },
              { label: 'Salary today', value: salaryToday > 0 ? `+${formatMoney(salaryToday)}` : 'No salary yet', tone: salaryToday > 0 ? 'positive' : 'neutral' },
              { label: 'Payment status', value: salaryStatus, tone: salaryStatus.toLowerCase().includes('failed') ? 'danger' : salaryToday > 0 ? 'positive' : 'warning' },
              { label: 'Job level', value: jobLevelLabel, tone: jobProgress ? 'positive' : 'neutral' },
              { label: 'Next salary', value: nextSalaryLabel, tone: jobProgress ? 'info' : 'neutral' },
              { label: 'Pay model', value: payModelLabel, tone: 'info' },
              { label: 'Stress', value: `${Math.round(stats?.stress ?? 0)}`, tone: (stats?.stress ?? 0) >= 65 ? 'danger' : 'warning' },
              { label: 'Health', value: `${Math.round(stats?.health ?? 100)}`, tone: (stats?.health ?? 100) >= 65 ? 'positive' : 'warning' },
              {
                label: 'Time left',
                value: `${loop.dailySession.remainingTimeUnits}/${loop.dailySession.totalTimeUnits}`,
                tone: loop.dailySession.remainingTimeUnits <= 2 ? 'warning' : 'info',
              },
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
        <View style={styles.metricRow}>
          <GameplayStatCard
            label="Today's pay"
            value={loop.jobIncome.dailyIncomeLabel}
            tone={loop.jobIncome.incomeAmount != null && loop.jobIncome.incomeAmount >= 0 ? 'positive' : 'warning'}
            note={loop.jobIncome.currentJob ? loop.jobIncome.currentJob.replace(/_/g, ' ') : 'No job selected yet'}
          />
          <GameplayStatCard
            label="Time cost"
            value={`${BALANCE.REALTIME.MINUTES_PER_UNIT} min / unit`}
            tone="info"
            note="Map actions spend time through the daily session rules."
          />
        </View>
      </GameplaySummaryCard>

      {actionHubForDisplay ? (
        <OnboardingHighlight target="work-first-action">
          <ActionHubPanel
            hub={actionHubForDisplay}
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

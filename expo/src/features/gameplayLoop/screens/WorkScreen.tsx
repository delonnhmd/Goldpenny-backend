import React, { useEffect, useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import ActionHubPanel from '@/components/gameplay/ActionHubPanel';
import ActionPreviewModal from '@/components/gameplay/ActionPreviewModal';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { recordInfo } from '@/lib/logger';
import { DailyActionItem } from '@/types/gameplay';

import { useGameplayLoop } from '../context';
import {
  GameplayStatCard,
  GameplayStickyActionArea,
  GameplaySummaryCard,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

interface StarterJobOption {
  job_key: string;
  title: string;
  monthly_pay_xgp: number;
  stability_weight: number;
  performance_weight: number;
  stress_sensitivity: number;
}

const INTERACTION_DIAGNOSTICS_ENABLED =
  __DEV__
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

function asStarterJobOptions(raw: unknown): StarterJobOption[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry) => {
      const row = entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
      const job_key = String(row.job_key || '').trim();
      if (!job_key) return null;
      return {
        job_key,
        title: String(row.title || job_key),
        monthly_pay_xgp: Number(row.monthly_pay_xgp || 0) || 0,
        stability_weight: Number(row.stability_weight || 0) || 0,
        performance_weight: Number(row.performance_weight || 0) || 0,
        stress_sensitivity: Number(row.stress_sensitivity || 0) || 0,
      };
    })
    .filter((entry): entry is StarterJobOption => Boolean(entry));
}

export default function WorkScreen() {
  useScreenTimer('work');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const guidedWorkActive = onboarding.isActive && onboarding.currentStep?.route === 'work';
  const simplified = onboarding.isSimplifiedMode;
  const stats = loop.dashboard?.stats;
  const endDayDisabled = !loop.dailyProgression.canAdvanceDay || loop.endingDay;
  const switchJobAction = useMemo(() => {
    if (!loop.actionHub) return null;
    return (
      [...(loop.actionHub.recommended_actions || []), ...(loop.actionHub.available_actions || [])]
        .find((action) => String(action.action_key || '').toLowerCase() === 'switch_job')
      || null
    );
  }, [loop.actionHub]);
  const starterJobOptions = useMemo(
    () => asStarterJobOptions(switchJobAction?.parameters?.job_options),
    [switchJobAction?.parameters?.job_options],
  );
  const currentJobKey = String(
    loop.actionHub?.debug_meta?.current_job_key
    || loop.dashboard?.stats?.current_job
    || '',
  ).trim();
  const hasStarterJobSelected = Boolean(
    loop.actionHub?.debug_meta?.has_starter_job_selected
    ?? currentJobKey,
  );
  const firstSessionFlag = Boolean(
    loop.dashboard?.debug_meta?.new_player_first_session
    ?? loop.actionHub?.debug_meta?.new_player_first_session
    ?? false,
  );
  const showStarterJobChooser = starterJobOptions.length > 0 && (firstSessionFlag || !hasStarterJobSelected);
  const selectingStarterJob = loop.executingAction && loop.busyActionKey === 'switch_job';

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Work starter job selection visibility evaluated.', {
      action: 'job_selection_visibility',
      context: {
        playerId: loop.playerId,
        firstSessionFlag,
        showStarterJobChooser,
        starterJobOptionsCount: starterJobOptions.length,
        hasStarterJobSelected,
        currentJobKey: currentJobKey || null,
      },
    });
  }, [
    currentJobKey,
    firstSessionFlag,
    hasStarterJobSelected,
    loop.playerId,
    showStarterJobChooser,
    starterJobOptions.length,
  ]);

  const selectStarterJob = (job: StarterJobOption) => {
    const template: DailyActionItem = switchJobAction || {
      action_key: 'switch_job',
      title: 'Choose Your First Job',
      description: 'Select one starter role to unlock work-shift income.',
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'unknown',
      parameters: {},
    };

    const action: DailyActionItem = {
      ...template,
      title: hasStarterJobSelected ? `Switch To ${job.title}` : `Choose ${job.title}`,
      status: 'available',
      parameters: {
        ...(template.parameters || {}),
        new_job_key: job.job_key,
        job_key: job.job_key,
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

      {showStarterJobChooser ? (
        <GameplaySummaryCard
          eyebrow={hasStarterJobSelected ? 'Starter role active' : 'Day 1 required step'}
          title={hasStarterJobSelected ? 'Switch Job (Optional)' : 'Choose Your First Job'}
          subtitle={hasStarterJobSelected
            ? `Current role: ${currentJobKey.replace(/_/g, ' ') || 'not set'}. You can keep it or switch lanes.`
            : 'Pick one role to unlock reliable work shifts and stabilize Day 1 cashflow.'}
        >
          <View style={styles.jobOptionsGrid}>
            {starterJobOptions.map((job) => {
              const isCurrent = currentJobKey === job.job_key;
              return (
                <View key={job.job_key} style={[styles.jobOptionCard, isCurrent ? styles.jobOptionCardActive : null]}>
                  <Text style={styles.jobTitle}>{job.title}</Text>
                  <Text style={styles.jobPay}>~{Math.round(job.monthly_pay_xgp)} xgp/mo</Text>
                  <Text style={styles.jobMeta}>
                    Stability {job.stability_weight.toFixed(2)} · Performance {job.performance_weight.toFixed(2)} · Stress {job.stress_sensitivity.toFixed(2)}
                  </Text>
                  <Pressable
                    accessibilityRole="button"
                    style={[
                      styles.jobSelectButton,
                      isCurrent ? styles.jobSelectButtonCurrent : null,
                      selectingStarterJob ? styles.jobSelectButtonDisabled : null,
                    ]}
                    disabled={selectingStarterJob || isCurrent}
                    onPress={() => {
                      selectStarterJob(job);
                    }}
                  >
                    <Text style={[styles.jobSelectButtonLabel, isCurrent ? styles.jobSelectButtonLabelCurrent : null]}>
                      {isCurrent ? 'Current Job' : selectingStarterJob ? 'Applying...' : 'Select Job'}
                    </Text>
                  </Pressable>
                </View>
              );
            })}
          </View>
        </GameplaySummaryCard>
      ) : null}

      {loop.actionHub ? (
        <OnboardingHighlight target="work-first-action">
          <ActionHubPanel
            hub={loop.actionHub}
            onPreviewAction={(action) => {
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
  jobOptionsGrid: {
    gap: theme.spacing.sm,
  },
  jobOptionCard: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  jobOptionCardActive: {
    borderColor: '#86efac',
    backgroundColor: '#f0fdf4',
  },
  jobTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.bodyMd,
    fontWeight: '800',
  },
  jobPay: {
    color: theme.color.info,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  jobMeta: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
  },
  jobSelectButton: {
    minHeight: 40,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    borderColor: '#1d4ed8',
    backgroundColor: '#1d4ed8',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.sm,
  },
  jobSelectButtonCurrent: {
    borderColor: '#16a34a',
    backgroundColor: '#dcfce7',
  },
  jobSelectButtonDisabled: {
    opacity: 0.7,
  },
  jobSelectButtonLabel: {
    color: '#ffffff',
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  jobSelectButtonLabelCurrent: {
    color: '#166534',
  },
});

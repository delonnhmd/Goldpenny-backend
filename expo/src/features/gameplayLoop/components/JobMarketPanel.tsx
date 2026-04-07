import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { JobMarketJobSnapshot, WorkJobMarketSnapshot } from '@/types/gameplay';

import { GameplaySummaryCard, GameplayWarningBanner } from './GameplayUIParts';

interface JobMarketPanelProps {
  jobMarket: WorkJobMarketSnapshot | null | undefined;
  executingAction: boolean;
  busyActionKey: string | null;
  onSwitchJob: (job: JobMarketJobSnapshot) => void;
  onStartTraining: (job: JobMarketJobSnapshot) => void;
}

export default function JobMarketPanel({
  jobMarket,
  executingAction,
  busyActionKey,
  onSwitchJob,
  onStartTraining,
}: JobMarketPanelProps) {
  if (!jobMarket || !Array.isArray(jobMarket.jobs) || jobMarket.jobs.length === 0) {
    return null;
  }

  const busySwitch = executingAction && busyActionKey === 'switch_job';
  const busyTraining = executingAction && busyActionKey === 'start_training';

  return (
    <GameplaySummaryCard
      eyebrow="Career Progression"
      title="Job Market"
      subtitle={jobMarket.has_main_job
        ? `Current job: ${jobMarket.current_job_display_name || 'Unknown'}`
        : "You don't have a job yet. Choose a job to start earning."}
    >
      {!jobMarket.has_main_job ? (
        <GameplayWarningBanner
          title="No main job assigned"
          message="You don't have a job yet. Choose a job in Job Market before starting a shift."
          tone="warning"
        />
      ) : null}

      {jobMarket.training_active ? (
        <GameplayWarningBanner
          title={`Training: ${jobMarket.training_certification_name || 'Certification'}`}
          message={`Progress ${Math.max(0, Number(jobMarket.training_days_completed || 0))} / ${Math.max(0, Number(jobMarket.training_days_required || 0))} days - ${Math.max(0, Number(jobMarket.training_days_remaining || 0))} remaining`}
          tone="info"
        />
      ) : null}

      <View style={styles.list}>
        {jobMarket.jobs.map((job) => {
          const status = String(job.status || '').toLowerCase();
          const isCurrent = Boolean(job.is_current_job || status === 'current');
          const isLocked = status === 'locked' || Boolean(job.is_future_unlock);
          const canSwitch = Boolean(job.can_switch) && !isCurrent && !isLocked;
          const canTrain = Boolean(job.can_start_training) && !Boolean(job.is_future_unlock);
          const trainingInProgress = Boolean(job.training_in_progress);
          const salary = Math.max(0, Number(job.base_salary_xgp || 0));
          const trainingProgress = trainingInProgress
            ? `${Math.max(0, Number(job.training_days_completed || 0))} / ${Math.max(0, Number(job.training_days_required || 0))}`
            : null;

          return (
            <View key={job.job_key} style={[styles.jobCard, isCurrent ? styles.jobCardCurrent : null]}>
              <View style={styles.jobHeader}>
                <Text style={styles.jobName}>{job.display_name}</Text>
                <Text style={styles.jobStatus}>
                  {isCurrent ? 'Current Job' : isLocked ? 'Locked' : 'Available'}
                </Text>
              </View>
              <Text style={styles.jobMeta}>Salary: {Math.round(salary)} XGP / month</Text>
              <Text style={styles.jobMeta}>Stress: {job.stress_level || 'Moderate'}</Text>
              <Text style={styles.jobMeta}>
                Requirement: {job.requires_certification ? `Requires ${job.certification_name || 'Certification'}` : 'No certification needed'}
              </Text>
              {trainingProgress ? (
                <Text style={styles.trainingMeta}>Training progress: {trainingProgress} days</Text>
              ) : null}

              {canSwitch ? (
                <PrimaryButton
                  label={busySwitch ? 'Switching...' : `Switch to ${job.display_name}`}
                  disabled={busySwitch || busyTraining}
                  onPress={() => onSwitchJob(job)}
                  style={styles.button}
                />
              ) : canTrain ? (
                <SecondaryButton
                  label={busyTraining ? 'Starting...' : 'Start Training'}
                  disabled={busyTraining || busySwitch}
                  onPress={() => onStartTraining(job)}
                  style={styles.button}
                />
              ) : (
                <SecondaryButton
                  label={isCurrent ? 'Current Job' : job.is_future_unlock ? 'Future Unlock' : 'Locked'}
                  disabled
                  style={styles.button}
                />
              )}
            </View>
          );
        })}
      </View>
    </GameplaySummaryCard>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: theme.spacing.sm,
  },
  jobCard: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  jobCardCurrent: {
    borderColor: '#86efac',
    backgroundColor: '#f0fdf4',
  },
  jobHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  jobName: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
    flex: 1,
  },
  jobStatus: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  jobMeta: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  trainingMeta: {
    ...theme.typography.caption,
    color: theme.color.info,
    fontWeight: '700',
  },
  button: {
    marginTop: theme.spacing.xs,
  },
});


import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { formatMoney } from '@/lib/gameplayFormatters';
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
  const currentJobProgress = jobMarket.jobs.find((job) => Boolean(job.is_current_job))?.progression || null;
  const currentJobName = jobMarket.current_job_display_name || 'No job selected';
  const currentJobXp = Math.max(0, Number(currentJobProgress?.job_xp || 0));
  const currentJobXpToNext = Math.max(0, Number(currentJobProgress?.job_xp_to_next_level || 0));
  const currentJobProgressPct = currentJobXpToNext > 0
    ? Math.max(0, Math.min(100, (currentJobXp / currentJobXpToNext) * 100))
    : 100;

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

      {currentJobProgress ? (
        <View style={styles.progressCard}>
          <Text style={styles.progressTitle}>Current Job Progress</Text>
          <Text style={styles.progressSubtitle}>
            {currentJobName} · Level {Math.max(1, Number(currentJobProgress.job_level || 1))}
            {' · '}
            {currentJobProgress.promotion_tier || 'Junior'}
          </Text>
          <Text style={styles.progressMeta}>
            XP: {Math.round(currentJobXp)} / {Math.round(currentJobXpToNext)}
          </Text>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${currentJobProgressPct}%` }]} />
          </View>
          <Text style={styles.progressMeta}>
            Shifts completed: {Math.max(0, Number(currentJobProgress.shifts_completed || 0))}
          </Text>
          <Text style={styles.progressMetaStrong}>
            Next level estimate: {formatMoney(Number(currentJobProgress.estimated_next_level_monthly_salary_xgp || 0))} / month
          </Text>
          <Text style={styles.progressHint}>
            {currentJobProgress.salary_preview_note || 'Estimated only - live payroll remains unchanged.'}
          </Text>
        </View>
      ) : null}

      {Array.isArray(jobMarket.career_progression) && jobMarket.career_progression.length > 0 ? (
        <View style={styles.careerListWrap}>
          <Text style={styles.careerListTitle}>Career Progression (All Jobs)</Text>
          {jobMarket.career_progression.map((track) => {
            const trackXp = Math.max(0, Number(track.job_xp || 0));
            const trackXpToNext = Math.max(0, Number(track.job_xp_to_next_level || 0));
            const trackPct = trackXpToNext > 0
              ? Math.max(0, Math.min(100, (trackXp / trackXpToNext) * 100))
              : 100;
            const locked = Boolean(track.locked);
            const hasProgress = Boolean(track.has_progression);
            return (
              <View key={`career_track_${track.job_key}`} style={styles.careerTrackRow}>
                <View style={styles.careerTrackHead}>
                  <Text style={styles.careerTrackJob}>{track.display_name || track.job_key}</Text>
                  <Text style={styles.careerTrackStatus}>
                    {locked ? 'Locked' : `Level ${Math.max(1, Number(track.job_level || 1))} · ${track.promotion_tier || 'Junior'}`}
                  </Text>
                </View>
                {locked ? (
                  <Text style={styles.careerTrackRequirement}>
                    {track.requirement_label || 'Certification required'}
                  </Text>
                ) : null}
                {hasProgress ? (
                  <>
                    <Text style={styles.careerTrackMeta}>
                      XP {Math.round(trackXp)} / {Math.round(trackXpToNext)} · Shifts {Math.max(0, Number(track.shifts_completed || 0))}
                    </Text>
                    <View style={styles.trackRowProgress}>
                      <View style={[styles.trackRowProgressFill, { width: `${trackPct}%` }]} />
                    </View>
                  </>
                ) : (
                  <Text style={styles.careerTrackMetaMuted}>
                    No progression yet.
                  </Text>
                )}
              </View>
            );
          })}
        </View>
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
          const progression = job.progression || null;
          const progressXp = Math.max(0, Number(progression?.job_xp || 0));
          const progressXpToNext = Math.max(0, Number(progression?.job_xp_to_next_level || 0));
          const progressPct = progressXpToNext > 0
            ? Math.max(0, Math.min(100, (progressXp / progressXpToNext) * 100))
            : 100;
          const currentSalaryEstimate = Number(progression?.estimated_current_monthly_salary_xgp || 0);
          const nextSalaryEstimate = Number(progression?.estimated_next_level_monthly_salary_xgp || 0);
          const nextPct = Number(progression?.next_level_salary_increase_pct || 3);

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
              {progression ? (
                <View style={styles.jobProgressWrap}>
                  <Text style={styles.jobProgressLabel}>
                    Level {Math.max(1, Number(progression.job_level || 1))} · {progression.promotion_tier || 'Junior'}
                  </Text>
                  <Text style={styles.jobProgressMeta}>
                    XP {Math.round(progressXp)} / {Math.round(progressXpToNext)} · Shifts {Math.max(0, Number(progression.shifts_completed || 0))}
                  </Text>
                  <View style={styles.trackRowProgress}>
                    <View style={[styles.trackRowProgressFill, { width: `${progressPct}%` }]} />
                  </View>
                  <Text style={styles.jobProgressMeta}>
                    Estimated current: {formatMoney(currentSalaryEstimate)} / month
                  </Text>
                  <Text style={styles.jobProgressMeta}>
                    Next level (+{Math.round(nextPct)}%): {formatMoney(nextSalaryEstimate)} / month
                  </Text>
                </View>
              ) : null}
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
  progressCard: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    backgroundColor: '#eff6ff',
    borderRadius: theme.radius.lg,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  progressTitle: {
    ...theme.typography.bodyMd,
    color: '#1e3a8a',
    fontWeight: '800',
  },
  progressSubtitle: {
    ...theme.typography.bodySm,
    color: '#1e40af',
    fontWeight: '700',
  },
  progressMeta: {
    ...theme.typography.caption,
    color: '#1e40af',
  },
  progressMetaStrong: {
    ...theme.typography.bodySm,
    color: '#1e3a8a',
    fontWeight: '700',
  },
  progressHint: {
    ...theme.typography.caption,
    color: '#1e40af',
  },
  progressTrack: {
    height: 7,
    borderRadius: theme.radius.pill,
    backgroundColor: '#dbeafe',
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#2563eb',
    borderRadius: theme.radius.pill,
  },
  careerListWrap: {
    gap: theme.spacing.xs,
  },
  careerListTitle: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  careerTrackRow: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    gap: theme.spacing.xxs,
  },
  careerTrackHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  careerTrackJob: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    fontWeight: '700',
    flex: 1,
  },
  careerTrackStatus: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    fontWeight: '700',
  },
  careerTrackRequirement: {
    ...theme.typography.caption,
    color: '#92400e',
    fontWeight: '700',
  },
  careerTrackMeta: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  careerTrackMetaMuted: {
    ...theme.typography.caption,
    color: theme.color.muted,
  },
  trackRowProgress: {
    height: 6,
    borderRadius: theme.radius.pill,
    backgroundColor: '#e5e7eb',
    overflow: 'hidden',
  },
  trackRowProgressFill: {
    height: '100%',
    backgroundColor: '#2563eb',
    borderRadius: theme.radius.pill,
  },
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
  jobProgressWrap: {
    marginTop: theme.spacing.xxs,
    gap: theme.spacing.xxs,
  },
  jobProgressLabel: {
    ...theme.typography.caption,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
  jobProgressMeta: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  button: {
    marginTop: theme.spacing.xs,
  },
});


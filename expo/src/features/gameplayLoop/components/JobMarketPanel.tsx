import { MaterialCommunityIcons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import Card from '@/components/ui/Card';
import Chip from '@/components/ui/Chip';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { BALANCE } from '@/lib/balanceConfig';
import { formatMoney } from '@/lib/gameplayFormatters';
import { JobMarketJobSnapshot, WorkJobMarketSnapshot } from '@/types/gameplay';

import { GameplaySummaryCard, GameplayWarningBanner } from './GameplayUIParts';

interface JobMarketPanelProps {
  jobMarket: WorkJobMarketSnapshot | null | undefined;
  executingAction: boolean;
  busyActionKey: string | null;
  onSwitchJob: (job: JobMarketJobSnapshot) => void;
  onStartTraining: (job: JobMarketJobSnapshot) => void;
  interactionDisabledReason?: string | null;
}

export default function JobMarketPanel({
  jobMarket,
  executingAction,
  busyActionKey,
  onSwitchJob,
  onStartTraining,
  interactionDisabledReason = null,
}: JobMarketPanelProps) {
  if (!jobMarket || !Array.isArray(jobMarket.jobs) || jobMarket.jobs.length === 0) {
    return null;
  }

  const busySwitch = executingAction && busyActionKey === 'switch_job';
  const busyTraining = executingAction && busyActionKey === 'start_training';
  const currentJobProgress = jobMarket.jobs.find((job) => Boolean(job.is_current_job))?.progression || null;
  const currentJobName = jobMarket.current_job_display_name || 'No job selected';
  const jobSyncStatus = String(jobMarket.job_sync_status || '').trim().toLowerCase();
  const jobSyncWarningMessage = String(jobMarket.job_sync_warning_message || '').trim();
  const currentJobXp = Math.max(0, Number(currentJobProgress?.job_xp || 0));
  const currentJobXpToNext = Math.max(0, Number(currentJobProgress?.job_xp_to_next_level || 0));
  const currentJobProgressPct = currentJobXpToNext > 0
    ? Math.max(0, Math.min(100, (currentJobXp / currentJobXpToNext) * 100))
    : 100;
  const switchJobUnitLabel = `${Math.max(0, Number(BALANCE.ACTION_TIME_COST.switch_job || 1))}u`;
  const trainingUnitLabel = '1u';
  const interactionsLocked = Boolean(interactionDisabledReason);

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
          title={jobSyncStatus === 'repair_needed' ? 'Job Data Syncing' : 'No Main Job Assigned'}
          message={
            jobSyncStatus === 'repair_needed'
              ? (jobSyncWarningMessage || 'Your job data is syncing. Please retry in a moment.')
              : "You don't have a job yet. Choose a job in Job Market before starting a shift."
          }
          tone="warning"
        />
      ) : null}

      {jobMarket.training_active ? (
        <GameplayWarningBanner
          title={`Training: ${jobMarket.training_certification_name || 'Certification'}`}
          message={`Progress ${Math.max(0, Number(jobMarket.training_days_completed || 0))} / ${Math.max(0, Number(jobMarket.training_days_required || 0))} days - ${Math.max(0, Number(jobMarket.training_days_remaining || 0))} remaining. Use Skill Training to advance progress.`}
          tone="info"
        />
      ) : null}

      {interactionsLocked ? (
        <GameplayWarningBanner
          title="Job Center Actions Locked"
          message={interactionDisabledReason || 'Travel to the Job Center before applying or starting training.'}
          tone="warning"
        />
      ) : null}

      {currentJobProgress ? (
        <Card variant="info" style={styles.progressCard}>
          <View style={styles.progressHeader}>
            <View style={styles.progressCopy}>
              <Text style={styles.progressTitle}>Current Job Progress</Text>
              <Text style={styles.progressSubtitle}>
                {currentJobName} | Level {Math.max(1, Number(currentJobProgress.job_level || 1))}
                {' | '}
                {currentJobProgress.promotion_tier || 'Junior'}
              </Text>
            </View>
            <Chip label="Current" variant="info" />
          </View>
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
        </Card>
      ) : null}

      {Array.isArray(jobMarket.career_progression) && jobMarket.career_progression.length > 0 ? (
        <View style={styles.careerListWrap}>
          <Text style={styles.careerListTitle}>Career Progression</Text>
          {jobMarket.career_progression.map((track) => {
            const trackXp = Math.max(0, Number(track.job_xp || 0));
            const trackXpToNext = Math.max(0, Number(track.job_xp_to_next_level || 0));
            const trackPct = trackXpToNext > 0
              ? Math.max(0, Math.min(100, (trackXp / trackXpToNext) * 100))
              : 100;
            const locked = Boolean(track.locked);
            const hasProgress = Boolean(track.has_progression);
            const cardVariant = locked ? 'warning' : hasProgress ? 'info' : 'default';
            const statusChipVariant = locked ? 'warning' : hasProgress ? 'info' : 'neutral';
            return (
              <Card key={`career_track_${track.job_key}`} variant={cardVariant} style={styles.careerTrackRow}>
                <View style={styles.careerTrackHead}>
                  <View style={styles.careerTrackCopy}>
                    <Text style={[styles.careerTrackJob, locked ? styles.lockedText : null]}>
                      {track.display_name || track.job_key}
                    </Text>
                    <Text style={styles.careerTrackStatus}>
                      {locked
                        ? 'Certification required'
                        : `Level ${Math.max(1, Number(track.job_level || 1))} | ${track.promotion_tier || 'Junior'}`}
                    </Text>
                  </View>
                  <Chip
                    label={locked ? 'Locked' : hasProgress ? 'Progress' : 'Open'}
                    variant={statusChipVariant}
                  />
                </View>
                {locked ? (
                  <View style={styles.lockedRow}>
                    <MaterialCommunityIcons name="lock-outline" size={14} color={theme.ui.warning} />
                    <Text style={styles.lockedHint}>
                      {track.requirement_label || 'Certification required'}
                    </Text>
                  </View>
                ) : null}
                {hasProgress ? (
                  <>
                    <Text style={styles.careerTrackMeta}>
                      XP {Math.round(trackXp)} / {Math.round(trackXpToNext)} | Shifts {Math.max(0, Number(track.shifts_completed || 0))}
                    </Text>
                    <View style={styles.trackRowProgress}>
                      <View style={[styles.trackRowProgressFill, { width: `${trackPct}%` }]} />
                    </View>
                  </>
                ) : (
                  <Text style={styles.careerTrackMetaMuted}>No progression yet.</Text>
                )}
              </Card>
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
          const progression = job.progression || null;
          const progressXp = Math.max(0, Number(progression?.job_xp || 0));
          const progressXpToNext = Math.max(0, Number(progression?.job_xp_to_next_level || 0));
          const progressPct = progressXpToNext > 0
            ? Math.max(0, Math.min(100, (progressXp / progressXpToNext) * 100))
            : 100;
          const currentSalaryEstimate = Number(progression?.estimated_current_monthly_salary_xgp || 0);
          const nextSalaryEstimate = Number(progression?.estimated_next_level_monthly_salary_xgp || 0);
          const nextPct = Number(progression?.next_level_salary_increase_pct || 3);
          const prerequisiteLine = Array.isArray(job.prerequisite_job_labels) && job.prerequisite_job_labels.length > 0
            ? job.prerequisite_job_labels.join(' / ')
            : 'Any starter lane';
          const cardVariant = isCurrent ? 'positive' : isLocked ? 'warning' : 'default';
          const statusVariant = isCurrent ? 'positive' : isLocked ? 'warning' : 'neutral';
          const lockedCopyStyle = isLocked ? styles.lockedText : null;

          return (
            <Card key={job.job_key} variant={cardVariant} style={styles.jobCard}>
              <View style={styles.jobHeader}>
                <Text style={[styles.jobName, lockedCopyStyle]}>{job.display_name}</Text>
                <Chip
                  label={isCurrent ? 'Current' : isLocked ? 'Locked' : 'Available'}
                  variant={statusVariant}
                />
              </View>
              <Text style={[styles.jobMeta, lockedCopyStyle]}>Salary: {Math.round(salary)} XGP / month</Text>
              <Text style={[styles.jobMeta, lockedCopyStyle]}>Stress: {job.stress_level || 'Moderate'}</Text>
              <Text style={[styles.jobMeta, lockedCopyStyle]}>
                Requirement: {job.requires_certification ? `Requires ${job.certification_name || 'Certification'}` : 'No certification needed'}
              </Text>
              <Text style={[styles.jobMeta, lockedCopyStyle]}>
                Level requirement: {Math.max(1, Number(job.level_requirement || 1))}
              </Text>
              <Text style={[styles.jobMeta, lockedCopyStyle]}>
                Experience requirement: {Math.max(0, Number(job.experience_requirement_shifts || 0))} total shifts
              </Text>
              <Text style={[styles.jobMeta, lockedCopyStyle]}>Path: {job.path_hint || prerequisiteLine}</Text>

              {isLocked ? (
                <View style={styles.lockedRow}>
                  <MaterialCommunityIcons name="lock-outline" size={14} color={theme.ui.warning} />
                  <Text style={styles.lockedHint}>{job.requirement_label || 'Finish the unlock requirement first.'}</Text>
                </View>
              ) : null}

              {progression ? (
                <View style={styles.jobProgressWrap}>
                  <Text style={[styles.jobProgressLabel, lockedCopyStyle]}>
                    Level {Math.max(1, Number(progression.job_level || 1))} | {progression.promotion_tier || 'Junior'}
                  </Text>
                  <Text style={[styles.jobProgressMeta, lockedCopyStyle]}>
                    XP {Math.round(progressXp)} / {Math.round(progressXpToNext)} | Shifts {Math.max(0, Number(progression.shifts_completed || 0))}
                  </Text>
                  <View style={styles.trackRowProgress}>
                    <View style={[styles.trackRowProgressFill, { width: `${progressPct}%` }]} />
                  </View>
                  <Text style={[styles.jobProgressMeta, lockedCopyStyle]}>
                    Estimated current: {formatMoney(currentSalaryEstimate)} / month
                  </Text>
                  <Text style={[styles.jobProgressMeta, lockedCopyStyle]}>
                    Next level (+{Math.round(nextPct)}%): {formatMoney(nextSalaryEstimate)} / month
                  </Text>
                </View>
              ) : null}

              {trainingInProgress ? (
                <View style={styles.trainingWrap}>
                  <Text style={styles.trainingTitle}>
                    Training: {job.certification_name || 'Certification'}
                  </Text>
                  <View style={styles.trainingProgressRow}>
                    <View style={styles.trainingTrack}>
                      <View
                        style={[
                          styles.trainingFill,
                          {
                            width: `${Math.max(0, Number(job.training_days_required || 0)) > 0
                              ? Math.min(100, (Math.max(0, Number(job.training_days_completed || 0)) / Math.max(1, Number(job.training_days_required || 0))) * 100)
                              : 0}%`,
                          },
                        ]}
                      />
                    </View>
                    <Text style={styles.trainingPct}>
                      {Math.max(0, Number(job.training_days_required || 0)) > 0
                        ? Math.round((Math.max(0, Number(job.training_days_completed || 0)) / Math.max(1, Number(job.training_days_required || 0))) * 100)
                        : 0}%
                    </Text>
                  </View>
                  <Text style={styles.trainingMeta}>
                    {Math.max(0, Number(job.training_days_completed || 0))} / {Math.max(0, Number(job.training_days_required || 0))} days completed | {Math.max(0, Number(job.training_days_remaining ?? (Number(job.training_days_required || 0) - Number(job.training_days_completed || 0))))} days remaining
                  </Text>
                  <Text style={styles.trainingHint}>Use Skill Training to advance progress.</Text>
                </View>
              ) : null}

              {isCurrent ? (
                <SecondaryButton
                  label="Current Job"
                  disabled
                  style={styles.button}
                />
              ) : canSwitch ? (
                <PrimaryButton
                  label={busySwitch ? 'Switching...' : `Switch to ${job.display_name}\n(${switchJobUnitLabel})`}
                  disabled={interactionsLocked || busySwitch || busyTraining}
                  onPress={() => onSwitchJob(job)}
                  style={styles.button}
                />
              ) : canTrain ? (
                <PrimaryButton
                  label={busyTraining ? 'Starting...' : `Start Training\n(${trainingUnitLabel})`}
                  disabled={interactionsLocked || busyTraining || busySwitch}
                  onPress={() => onStartTraining(job)}
                  style={styles.button}
                />
              ) : (
                <SecondaryButton
                  label="Locked"
                  disabled
                  style={styles.button}
                />
              )}
            </Card>
          );
        })}
      </View>
    </GameplaySummaryCard>
  );
}

const styles = StyleSheet.create({
  progressCard: {
    gap: theme.spacing.xs,
  },
  progressHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  progressCopy: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  progressTitle: {
    ...theme.typography.bodyMd,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  progressSubtitle: {
    ...theme.typography.bodySm,
    color: theme.ui.info,
    fontWeight: '700',
  },
  progressMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
  progressMetaStrong: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDark,
    fontWeight: '700',
  },
  progressHint: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
  progressTrack: {
    height: 7,
    borderRadius: theme.ui.radius.chip,
    backgroundColor: theme.ui.bg.cardRaised,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: theme.ui.info,
    borderRadius: theme.ui.radius.chip,
  },
  careerListWrap: {
    gap: theme.spacing.xs,
  },
  careerListTitle: {
    ...theme.typography.bodyMd,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  careerTrackRow: {
    gap: theme.spacing.xs,
  },
  careerTrackHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  careerTrackCopy: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  careerTrackJob: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDark,
    fontWeight: '700',
  },
  careerTrackStatus: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '700',
  },
  careerTrackMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
  careerTrackMetaMuted: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
  list: {
    gap: theme.spacing.sm,
  },
  jobCard: {
    gap: theme.spacing.xs,
  },
  jobHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  jobName: {
    ...theme.typography.bodyMd,
    color: theme.ui.text.onDark,
    fontWeight: '800',
    flex: 1,
  },
  jobMeta: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  lockedText: {
    color: theme.ui.text.onDarkMuted,
  },
  lockedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.xs,
  },
  lockedHint: {
    ...theme.typography.caption,
    color: theme.ui.warning,
    fontWeight: '700',
    flex: 1,
  },
  trackRowProgress: {
    height: 6,
    borderRadius: theme.ui.radius.chip,
    backgroundColor: theme.ui.bg.cardRaised,
    overflow: 'hidden',
  },
  trackRowProgressFill: {
    height: '100%',
    backgroundColor: theme.ui.info,
    borderRadius: theme.ui.radius.chip,
  },
  trainingWrap: {
    marginTop: theme.spacing.xxs,
    gap: theme.spacing.xxs,
  },
  trainingTitle: {
    ...theme.typography.caption,
    color: theme.ui.info,
    fontWeight: '800',
  },
  trainingProgressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.xs,
  },
  trainingTrack: {
    flex: 1,
    height: 8,
    borderRadius: theme.ui.radius.chip,
    backgroundColor: theme.ui.bg.cardRaised,
    overflow: 'hidden',
  },
  trainingFill: {
    height: '100%',
    backgroundColor: theme.ui.info,
    borderRadius: theme.ui.radius.chip,
  },
  trainingPct: {
    ...theme.typography.caption,
    color: theme.ui.info,
    fontWeight: '700',
    minWidth: 32,
    textAlign: 'right',
  },
  trainingMeta: {
    ...theme.typography.caption,
    color: theme.ui.info,
    fontWeight: '700',
  },
  trainingHint: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
  jobProgressWrap: {
    marginTop: theme.spacing.xxs,
    gap: theme.spacing.xxs,
  },
  jobProgressLabel: {
    ...theme.typography.caption,
    color: theme.ui.text.onDark,
    fontWeight: '700',
  },
  jobProgressMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
  button: {
    marginTop: theme.spacing.xs,
  },
});

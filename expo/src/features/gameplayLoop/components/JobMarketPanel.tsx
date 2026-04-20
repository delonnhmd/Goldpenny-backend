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

function salaryLabel(value: number): string {
  return `${Math.round(Math.max(0, Number(value || 0)))} XGP / month`;
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
          title={jobSyncStatus === 'repair_needed' ? 'Job Data Syncing' : 'No main job assigned'}
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
          <View style={styles.progressTitleRow}>
            <Text style={styles.progressTitle}>Current Job Progress</Text>
            <Chip
              label={`Level ${Math.max(1, Number(currentJobProgress.job_level || 1))}`}
              variant="active"
            />
          </View>
          <Text style={styles.progressSubtitle}>
            {currentJobName} | {currentJobProgress.promotion_tier || 'Junior'}
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
        </Card>
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
              <Card
                key={`career_track_${track.job_key}`}
                variant={locked ? 'warning' : 'default'}
                style={styles.careerTrackRow}
              >
                <View style={styles.careerTrackHead}>
                  <Text style={styles.careerTrackJob}>{track.display_name || track.job_key}</Text>
                  <Chip
                    label={locked ? 'Locked' : `Level ${Math.max(1, Number(track.job_level || 1))}`}
                    variant={locked ? 'warning' : 'neutral'}
                  />
                </View>
                {locked ? (
                  <Text style={styles.careerTrackRequirement}>
                    {track.requirement_label || 'Certification required'}
                  </Text>
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
                  <Text style={styles.careerTrackMetaMuted}>
                    No progression yet.
                  </Text>
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

          return (
            <Card key={job.job_key} variant={cardVariant} style={styles.jobCard}>
              <View style={styles.jobHeader}>
                <Text style={styles.jobName}>{job.display_name}</Text>
                {isCurrent ? <Chip label="Current" variant="positive" /> : null}
                {!isCurrent && isLocked ? (
                  <View style={styles.lockedStateWrap}>
                    <Text style={styles.lockIcon}>{'\u{1F512}'}</Text>
                    <Chip label="Locked" variant="warning" />
                  </View>
                ) : null}
              </View>
              <Text style={[styles.jobMeta, isLocked ? styles.jobMetaLocked : null]}>
                Salary: {salaryLabel(salary)}
              </Text>
              <Text style={[styles.jobMeta, isLocked ? styles.jobMetaLocked : null]}>
                Stress: {job.stress_level || 'Moderate'}
              </Text>
              <Text style={[styles.jobMeta, isLocked ? styles.jobMetaLocked : null]}>
                Requirement: {job.requires_certification ? `Requires ${job.certification_name || 'Certification'}` : 'No certification needed'}
              </Text>
              <Text style={[styles.jobMeta, isLocked ? styles.jobMetaLocked : null]}>
                Level requirement: {Math.max(1, Number(job.level_requirement || 1))}
              </Text>
              <Text style={[styles.jobMeta, isLocked ? styles.jobMetaLocked : null]}>
                Experience requirement: {Math.max(0, Number(job.experience_requirement_shifts || 0))} total shifts
              </Text>
              <Text style={[styles.jobMeta, isLocked ? styles.jobMetaLocked : null]}>
                Path: {job.path_hint || prerequisiteLine}
              </Text>
              {isLocked && job.requirement_label ? (
                <Text style={styles.lockedHint}>{job.requirement_label}</Text>
              ) : null}
              {progression ? (
                <View style={styles.jobProgressWrap}>
                  <Text style={[styles.jobProgressLabel, isLocked ? styles.jobMetaLocked : null]}>
                    Level {Math.max(1, Number(progression.job_level || 1))} | {progression.promotion_tier || 'Junior'}
                  </Text>
                  <Text style={[styles.jobProgressMeta, isLocked ? styles.jobMetaLocked : null]}>
                    XP {Math.round(progressXp)} / {Math.round(progressXpToNext)} | Shifts {Math.max(0, Number(progression.shifts_completed || 0))}
                  </Text>
                  <View style={styles.trackRowProgress}>
                    <View style={[styles.trackRowProgressFill, { width: `${progressPct}%` }]} />
                  </View>
                  <Text style={[styles.jobProgressMeta, isLocked ? styles.jobMetaLocked : null]}>
                    Estimated current: {formatMoney(currentSalaryEstimate)} / month
                  </Text>
                  <Text style={[styles.jobProgressMeta, isLocked ? styles.jobMetaLocked : null]}>
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

              {canSwitch ? (
                <PrimaryButton
                  label={busySwitch ? 'Switching...' : `Switch to ${job.display_name}\n(${switchJobUnitLabel})`}
                  disabled={interactionsLocked || busySwitch || busyTraining}
                  onPress={() => onSwitchJob(job)}
                  style={styles.button}
                />
              ) : trainingInProgress ? (
                <SecondaryButton
                  label="Training In Progress"
                  disabled
                  style={styles.button}
                />
              ) : canTrain ? (
                <SecondaryButton
                  label={busyTraining ? 'Starting...' : `Start Training\n(${trainingUnitLabel})`}
                  disabled={interactionsLocked || busyTraining || busySwitch}
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
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
  },
  progressTitleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  progressTitle: {
    ...theme.typography.bodyMd,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  progressSubtitle: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
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
    borderRadius: theme.radius.pill,
    backgroundColor: theme.ui.bg.cardRaised,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: theme.ui.action,
    borderRadius: theme.radius.pill,
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
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
  },
  careerTrackHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  careerTrackJob: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDark,
    fontWeight: '700',
    flex: 1,
  },
  careerTrackRequirement: {
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
  trackRowProgress: {
    height: 6,
    borderRadius: theme.radius.pill,
    backgroundColor: theme.ui.bg.cardRaised,
    overflow: 'hidden',
  },
  trackRowProgressFill: {
    height: '100%',
    backgroundColor: theme.ui.action,
    borderRadius: theme.radius.pill,
  },
  list: {
    gap: theme.spacing.sm,
  },
  jobCard: {
    gap: theme.spacing.xxs,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
  },
  jobHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  lockedStateWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.xs,
  },
  lockIcon: {
    fontSize: 14,
    color: theme.ui.warning,
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
  jobMetaLocked: {
    color: theme.ui.text.onDarkMuted,
  },
  lockedHint: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '700',
  },
  trainingWrap: {
    marginTop: theme.spacing.xxs,
    gap: theme.spacing.xxs,
  },
  trainingTitle: {
    ...theme.typography.caption,
    color: theme.ui.text.onDark,
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
    borderRadius: theme.radius.pill,
    backgroundColor: theme.ui.bg.cardRaised,
    overflow: 'hidden',
  },
  trainingFill: {
    height: '100%',
    backgroundColor: theme.ui.info,
    borderRadius: theme.radius.pill,
  },
  trainingPct: {
    ...theme.typography.caption,
    color: theme.ui.text.onDark,
    fontWeight: '700',
    minWidth: 32,
    textAlign: 'right',
  },
  trainingMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
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

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, BackHandler, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import type { DimensionValue } from 'react-native';
import { router } from 'expo-router';

import AnnualRecapCard from '@/components/gameplay/AnnualRecapCard';
import EndOfDaySummaryCard from '@/components/gameplay/EndOfDaySummaryCard';
import PrimaryButton from '@/components/ui/PrimaryButton';
import EmptyStateView from '@/components/ui/EmptyStateView';
import { alpha, theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { getPlayerAnnualRecap } from '@/lib/api/gameplay';
import { formatDelta, formatMoney } from '@/lib/gameplayFormatters';
import {
  AnnualRecapResponse,
  EndOfDaySummaryResponse,
  PlayerRunStatusResponse,
  TransactionHistoryItem,
} from '@/types/gameplay';

import { useGameplayLoop } from '../context';
import { toneFromSignedValue } from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

function formatBriefUnlockTime(value?: string | null): string {
  const raw = String(value || '').trim();
  const match = raw.match(/T(\d{2}):(\d{2})/);
  if (!match) return '7:00 AM';
  const hour24 = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isFinite(hour24) || !Number.isFinite(minute)) return '7:00 AM';
  const period = hour24 >= 12 ? 'PM' : 'AM';
  const hour12 = hour24 % 12 || 12;
  return `${hour12}:${String(minute).padStart(2, '0')} ${period}`;
}

export function SummaryMomentView({
  summary,
  transactions = [],
  missingAfterSettlement = false,
  endingDay = false,
  canAdvanceDay = true,
  retirementCard = null,
  annualRecapEntry = null,
  onRunSettlement,
  onContinueToTomorrow,
}: {
  summary: EndOfDaySummaryResponse | null;
  transactions?: TransactionHistoryItem[];
  missingAfterSettlement?: boolean;
  endingDay?: boolean;
  canAdvanceDay?: boolean;
  retirementCard?: React.ReactNode;
  annualRecapEntry?: React.ReactNode;
  onRunSettlement: () => void;
  onContinueToTomorrow: () => void;
}) {
  const headlineScale = useRef(new Animated.Value(0.96)).current;
  const headlineOpacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(headlineScale, { toValue: 1, duration: 360, useNativeDriver: true }),
      Animated.timing(headlineOpacity, { toValue: 1, duration: 320, useNativeDriver: true }),
    ]).start();
  }, [headlineOpacity, headlineScale, summary?.day_number, summary?.net_change_xgp]);

  if (!summary && missingAfterSettlement) {
    return (
      <View style={styles.screen}>
        <EmptyStateView
          title="Summary temporarily unavailable"
          subtitle="Settlement completed. Continue to tomorrow, then refresh later for full recap data."
        />
        {annualRecapEntry}
        <PrimaryButton
          testID="summary-continue-button"
          label="Continue to Tomorrow"
          onPress={onContinueToTomorrow}
        />
      </View>
    );
  }

  if (!summary) {
    return (
      <View style={styles.screen}>
        <EmptyStateView
          title="No settled summary yet"
          subtitle="Run settlement to generate today's closeout."
        />
        {annualRecapEntry}
        <PrimaryButton
          testID="summary-run-settlement-button"
          label={endingDay ? 'Settling Day...' : 'Run End Of Day Settlement'}
          loading={endingDay}
          disabled={!canAdvanceDay || endingDay}
          onPress={onRunSettlement}
        />
      </View>
    );
  }

  const netTone = toneFromSignedValue(summary.net_change_xgp);
  const tomorrowFocus = summary.guided_watch_tomorrow
    || summary.tomorrow_warnings[0]
    || (summary.net_change_xgp < 0
      ? 'Rebuild cash before taking extra risk.'
      : 'Protect the cash buffer, then choose one clear growth move.');

  return (
    <View style={styles.screen}>
      <Animated.View style={[styles.hero, { opacity: headlineOpacity, transform: [{ scale: headlineScale }] }]}>
        <Text style={styles.kicker}>Day {summary.day_number || summary.as_of_date} closed</Text>
        <Text style={styles.headline}>{formatMoney(summary.net_change_xgp)} net</Text>
        <Text style={styles.subhead}>
          {summary.net_change_xgp >= 0 ? 'Momentum survived today.' : 'Pressure hit today. Tomorrow is a recovery chance.'}
        </Text>
      </Animated.View>

      <View style={styles.moneyGrid}>
        <View style={styles.moneyCell}>
          <Text style={styles.metricLabel}>Earned</Text>
          <Text style={[styles.metricValue, styles.positive]}>{formatMoney(summary.total_earned_xgp)}</Text>
        </View>
        <View style={styles.moneyCell}>
          <Text style={styles.metricLabel}>Spent</Text>
          <Text style={[styles.metricValue, styles.negative]}>{formatMoney(-Math.abs(summary.total_spent_xgp))}</Text>
        </View>
        <View style={[styles.moneyCell, netTone === 'danger' ? styles.netNegative : styles.netPositive]}>
          <Text style={styles.metricLabel}>Net</Text>
          <Text style={[styles.metricValue, netTone === 'danger' ? styles.negative : styles.positive]}>
            {formatMoney(summary.net_change_xgp)}
          </Text>
        </View>
      </View>

      <View style={styles.storyGrid}>
        <View style={styles.storyPanel}>
          <Text style={styles.storyLabel}>Main gain</Text>
          <Text style={styles.storyValue}>{summary.biggest_gain}</Text>
          <View style={[styles.outcomeBar, styles.outcomeGain]} />
        </View>
        <View style={styles.storyPanel}>
          <Text style={styles.storyLabel}>Main drag</Text>
          <Text style={styles.storyValue}>{summary.biggest_loss}</Text>
          <View style={[styles.outcomeBar, styles.outcomeDrag]} />
        </View>
      </View>

      <View style={styles.chipRow}>
        <View style={styles.deltaChip}>
          <Text style={styles.deltaLabel}>Stress</Text>
          <Text style={styles.deltaValue}>{formatDelta(summary.stress_delta)}</Text>
        </View>
        <View style={styles.deltaChip}>
          <Text style={styles.deltaLabel}>Health</Text>
          <Text style={styles.deltaValue}>{formatDelta(summary.health_delta)}</Text>
        </View>
        <View style={styles.deltaChip}>
          <Text style={styles.deltaLabel}>Skill</Text>
          <Text style={styles.deltaValue}>{formatDelta(summary.skill_delta)}</Text>
        </View>
        <View style={styles.deltaChip}>
          <Text style={styles.deltaLabel}>Credit</Text>
          <Text style={styles.deltaValue}>{formatDelta(summary.credit_score_delta, 0)}</Text>
        </View>
      </View>

      {summary.tomorrow_warnings.length > 0 ? (
        <View style={styles.warningPanel}>
          <Text style={styles.panelTitle}>Warnings</Text>
          {summary.tomorrow_warnings.map((warning, index) => (
            <Text key={`warning_${index}`} style={styles.warningText}>{warning}</Text>
          ))}
        </View>
      ) : null}

      <EndOfDaySummaryCard summary={summary} transactions={transactions} />

      <View style={styles.tomorrowPanel}>
        <Text style={styles.panelTitle}>Tomorrow Focus</Text>
        <Text style={styles.unlockText}>
          Next brief unlocks at {formatBriefUnlockTime(summary.next_morning_brief_at || summary.tomorrow_preview_time)}
        </Text>
        <Text style={styles.tomorrowText}>{tomorrowFocus}</Text>
      </View>

      {retirementCard}
      {annualRecapEntry}

      <PrimaryButton
        testID="summary-continue-button"
        label="Continue to Tomorrow"
        onPress={onContinueToTomorrow}
      />
    </View>
  );
}

function RetirementEligibilityCard({
  runStatus,
  retiring,
  onRequestRetire,
}: {
  runStatus: PlayerRunStatusResponse | null;
  retiring: boolean;
  onRequestRetire: () => void;
}) {
  if (!runStatus || runStatus.run_status !== 'active') return null;

  const requirement = runStatus.retirement_requirement;
  const minDay = Math.max(1, Math.round(Number(requirement.min_day) || 30));
  const currentDay = Math.max(1, Math.round(Number(requirement.current_day) || 1));
  const minNetWorth = Math.max(1, Number(requirement.min_net_worth) || 10000);
  const currentNetWorth = Math.max(0, Number(requirement.current_net_worth) || 0);
  const dayProgress = `${Math.min(100, Math.max(0, (currentDay / minDay) * 100))}%` as DimensionValue;
  const wealthProgress = `${Math.min(100, Math.max(0, (currentNetWorth / minNetWorth) * 100))}%` as DimensionValue;
  const eligible = Boolean(runStatus.can_retire);

  return (
    <View style={[styles.retirementPanel, eligible ? styles.retirementEligible : null]}>
      <View style={styles.retirementHeader}>
        <View style={styles.retirementTitleBlock}>
          <Text style={styles.panelTitle}>Retirement</Text>
          <Text style={styles.retirementSubhead}>
            {eligible ? 'Eligible to close this run.' : 'Progress toward a victory ending.'}
          </Text>
        </View>
        <View style={[styles.eligibilityBadge, eligible ? styles.eligibilityBadgeReady : null]}>
          <Text style={styles.eligibilityText}>{eligible ? 'Eligible' : 'Locked'}</Text>
        </View>
      </View>

      <View style={styles.progressStack}>
        <View style={styles.progressItem}>
          <View style={styles.progressLabelRow}>
            <Text style={styles.progressLabel}>Day {minDay}</Text>
            <Text style={styles.progressValue}>{currentDay}/{minDay}</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: dayProgress }]} />
          </View>
        </View>
        <View style={styles.progressItem}>
          <View style={styles.progressLabelRow}>
            <Text style={styles.progressLabel}>{formatMoney(minNetWorth)} net worth</Text>
            <Text style={styles.progressValue}>{formatMoney(currentNetWorth)}</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: wealthProgress }]} />
          </View>
        </View>
      </View>

      <PrimaryButton
        testID="summary-retire-button"
        label={retiring ? 'Retiring...' : 'Retire Run'}
        loading={retiring}
        disabled={!eligible || retiring}
        onPress={onRequestRetire}
      />
    </View>
  );
}

function normalizeRecapError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error || '');
  const trimmed = raw.trim();
  if (!trimmed) return 'Recap is unavailable right now.';
  const firstColon = trimmed.indexOf(':');
  if (trimmed.startsWith('/player/') && firstColon > -1) {
    return trimmed.slice(firstColon + 1).trim() || 'Recap is unavailable right now.';
  }
  return trimmed;
}

function AnnualRecapEntry({
  currentDay,
  recap,
  loading,
  loadingMode,
  error,
  onViewYear,
  onViewDebug,
  onViewTimeline,
}: {
  currentDay: number;
  recap: AnnualRecapResponse | null;
  loading: boolean;
  loadingMode: 'year' | 'debug' | null;
  error: string | null;
  onViewYear: () => void;
  onViewDebug: () => void;
  onViewTimeline: () => void;
}) {
  const showYearButton = currentDay >= 365;
  const showDebugButton = currentDay >= 30 && currentDay < 365;
  if (!showYearButton && !showDebugButton && !recap && !error) return null;

  const isDebugRecap = Boolean(recap && Number(recap.days_survived) < 365);

  return (
    <View style={styles.annualRecapPanel}>
      <View style={styles.annualRecapHeader}>
        <Text style={styles.panelTitle}>Year-End Recap</Text>
        <Text style={styles.annualRecapSubhead}>
          Day {Math.max(1, Math.round(Number(currentDay) || 1))}
        </Text>
      </View>

      <View style={styles.annualRecapActions}>
        {showYearButton ? (
          <PrimaryButton
            testID="summary-year-recap-button"
            label={loading && loadingMode === 'year' ? 'Loading Recap...' : 'View Year Recap'}
            loading={loading && loadingMode === 'year'}
            disabled={loading}
            onPress={onViewYear}
            style={styles.annualRecapAction}
          />
        ) : null}
        {showDebugButton ? (
          <PrimaryButton
            testID="summary-debug-recap-button"
            label={loading && loadingMode === 'debug' ? 'Loading Preview...' : 'View 30-Day Recap Preview'}
            loading={loading && loadingMode === 'debug'}
            disabled={loading}
            onPress={onViewDebug}
            style={styles.annualRecapAction}
          />
        ) : null}
      </View>

      {error ? <Text style={styles.annualRecapError}>{error}</Text> : null}
      {recap ? (
        <AnnualRecapCard
          recap={recap}
          preview={isDebugRecap}
          onViewFullStory={onViewTimeline}
        />
      ) : null}
    </View>
  );
}

export default function SummaryScreen() {
  useScreenTimer('summary');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const summary = loop.endOfDaySummary;
  const missingAfterSettlement = !summary && loop.dailySession.sessionStatus === 'ended';
  const refreshRef = useRef(loop.refresh);
  const [retireConfirmVisible, setRetireConfirmVisible] = useState(false);
  const [retiring, setRetiring] = useState(false);
  const [annualRecap, setAnnualRecap] = useState<AnnualRecapResponse | null>(null);
  const [annualRecapLoading, setAnnualRecapLoading] = useState(false);
  const [annualRecapMode, setAnnualRecapMode] = useState<'year' | 'debug' | null>(null);
  const [annualRecapError, setAnnualRecapError] = useState<string | null>(null);

  const currentDay = useMemo(() => {
    const candidates = [
      summary?.day_number,
      loop.runStatus?.retirement_requirement?.current_day,
      loop.authoritativeState?.day_number,
      loop.dashboard?.work_state?.current_game_day,
      loop.actionHub?.work_state?.current_game_day,
      loop.dailyProgression.currentGameDay,
    ]
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value > 0);
    return Math.max(1, ...candidates.map((value) => Math.round(value)));
  }, [
    loop.actionHub?.work_state?.current_game_day,
    loop.authoritativeState?.day_number,
    loop.dailyProgression.currentGameDay,
    loop.dashboard?.work_state?.current_game_day,
    loop.runStatus?.retirement_requirement?.current_day,
    summary?.day_number,
  ]);

  useEffect(() => {
    refreshRef.current = loop.refresh;
  }, [loop.refresh]);

  useEffect(() => {
    setAnnualRecap(null);
    setAnnualRecapError(null);
    setAnnualRecapLoading(false);
    setAnnualRecapMode(null);
  }, [loop.playerId]);

  useEffect(() => {
    void refreshRef.current({ silent: true, includeEndOfDaySummary: true });
  }, [loop.playerId]);

  useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (retireConfirmVisible) {
        setRetireConfirmVisible(false);
        return true;
      }
      if (summary || missingAfterSettlement) return true;
      return false;
    });
    return () => {
      subscription.remove();
    };
  }, [missingAfterSettlement, retireConfirmVisible, summary]);

  const handleConfirmRetire = async () => {
    setRetiring(true);
    try {
      const result = await loop.retireRun();
      setRetireConfirmVisible(false);
      if (result.eligible) {
        router.replace(`/gameplay/loop/${loop.playerId}/end`);
      }
    } finally {
      setRetiring(false);
    }
  };

  const handleLoadAnnualRecap = async (debug: boolean) => {
    const mode = debug ? 'debug' : 'year';
    setAnnualRecapMode(mode);
    setAnnualRecapLoading(true);
    setAnnualRecapError(null);
    try {
      const payload = await getPlayerAnnualRecap(loop.playerId, { year: 1, debug });
      setAnnualRecap(payload);
    } catch (error) {
      const message = normalizeRecapError(error);
      setAnnualRecap(null);
      setAnnualRecapError(message);
      loop.setFeedback({ tone: 'error', message });
    } finally {
      setAnnualRecapLoading(false);
      setAnnualRecapMode(null);
    }
  };

  return (
    <>
      <GameplayLoopScaffold
        title="End Of Day"
        subtitle="Today's closeout and tomorrow setup"
        activeNavKey="summary"
      >
        <SummaryMomentView
          summary={summary}
          transactions={loop.dailyActivity?.transactions || []}
          missingAfterSettlement={missingAfterSettlement}
          endingDay={loop.endingDay}
          canAdvanceDay={loop.dailyProgression.canAdvanceDay}
          retirementCard={(
            <RetirementEligibilityCard
              runStatus={loop.runStatus}
              retiring={retiring}
              onRequestRetire={() => setRetireConfirmVisible(true)}
            />
          )}
          annualRecapEntry={(
            <AnnualRecapEntry
              currentDay={currentDay}
              recap={annualRecap}
              loading={annualRecapLoading}
              loadingMode={annualRecapMode}
              error={annualRecapError}
              onViewYear={() => {
                void handleLoadAnnualRecap(false);
              }}
              onViewDebug={() => {
                void handleLoadAnnualRecap(true);
              }}
              onViewTimeline={() => {
                router.push(`/gameplay/loop/${loop.playerId}/timeline`);
              }}
            />
          )}
          onRunSettlement={() => {
            void loop.endCurrentDay();
          }}
          onContinueToTomorrow={() => {
            void (async () => {
              await loop.startNextDay();
              onboarding.navigateTo('life');
            })();
          }}
        />
      </GameplayLoopScaffold>

      <Modal
        visible={retireConfirmVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setRetireConfirmVisible(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Retire Run?</Text>
            <Text style={styles.modalText}>Retiring ends this run permanently. Continue?</Text>
            <View style={styles.modalActions}>
              <Pressable
                testID="summary-retire-cancel-button"
                style={styles.modalSecondaryButton}
                disabled={retiring}
                onPress={() => setRetireConfirmVisible(false)}
              >
                <Text style={styles.modalSecondaryText}>Cancel</Text>
              </Pressable>
              <PrimaryButton
                testID="summary-retire-confirm-button"
                label={retiring ? 'Retiring...' : 'Retire Run'}
                loading={retiring}
                tone="danger"
                onPress={handleConfirmRetire}
                style={styles.modalPrimaryButton}
              />
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  screen: {
    gap: theme.spacing.lg,
  },
  hero: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.card,
    backgroundColor: theme.ui.bg.card,
    padding: theme.spacing.lg,
    gap: theme.spacing.xs,
  },
  kicker: {
    color: theme.ui.info,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  headline: {
    color: theme.ui.text.onDark,
    fontSize: 34,
    fontWeight: '900',
  },
  subhead: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.bodySm,
  },
  moneyGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  moneyCell: {
    flex: 1,
    minWidth: 98,
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  netPositive: {
    borderColor: theme.ui.positive,
  },
  netNegative: {
    borderColor: theme.ui.danger,
  },
  metricLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  metricValue: {
    color: theme.ui.text.onDark,
    fontSize: 18,
    fontWeight: '900',
  },
  positive: {
    color: theme.ui.positive,
  },
  negative: {
    color: theme.ui.danger,
  },
  storyGrid: {
    gap: theme.spacing.sm,
  },
  storyPanel: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  storyLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  storyValue: {
    color: theme.ui.text.onDark,
    ...theme.typography.bodyMd,
    fontWeight: '800',
  },
  outcomeBar: {
    height: 6,
    borderRadius: 999,
  },
  outcomeGain: {
    width: '88%',
    backgroundColor: theme.ui.positive,
  },
  outcomeDrag: {
    width: '64%',
    backgroundColor: theme.ui.danger,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  deltaChip: {
    flexGrow: 1,
    minWidth: 74,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    borderWidth: 1,
    borderColor: theme.ui.border,
    padding: theme.spacing.sm,
  },
  deltaLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  deltaValue: {
    color: theme.ui.text.onDark,
    ...theme.typography.bodySm,
    fontWeight: '800',
  },
  warningPanel: {
    borderWidth: 1,
    borderColor: theme.ui.danger,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  panelTitle: {
    color: theme.ui.text.onDark,
    ...theme.typography.label,
    fontWeight: '900',
  },
  warningText: {
    color: theme.ui.danger,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  tomorrowPanel: {
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  tomorrowText: {
    color: theme.ui.text.onDark,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  unlockText: {
    color: theme.ui.info,
    ...theme.typography.bodySm,
    fontWeight: '800',
  },
  retirementPanel: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.md,
  },
  retirementEligible: {
    borderColor: theme.ui.positive,
  },
  retirementHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: theme.spacing.md,
  },
  retirementTitleBlock: {
    flex: 1,
    gap: theme.spacing.xs,
  },
  retirementSubhead: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  eligibilityBadge: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 999,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 4,
    backgroundColor: theme.ui.bg.card,
  },
  eligibilityBadgeReady: {
    borderColor: theme.ui.positive,
  },
  eligibilityText: {
    color: theme.ui.text.onDark,
    ...theme.typography.caption,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  progressStack: {
    gap: theme.spacing.sm,
  },
  progressItem: {
    gap: theme.spacing.xs,
  },
  progressLabelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  progressLabel: {
    color: theme.ui.text.onDark,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  progressValue: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
  },
  progressTrack: {
    height: 7,
    borderRadius: 999,
    overflow: 'hidden',
    backgroundColor: theme.ui.bg.card,
    borderWidth: 1,
    borderColor: theme.ui.border,
  },
  progressFill: {
    height: '100%',
    borderRadius: 999,
    backgroundColor: theme.ui.positive,
  },
  annualRecapPanel: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.md,
  },
  annualRecapHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.md,
  },
  annualRecapSubhead: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  annualRecapActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  annualRecapAction: {
    flexGrow: 1,
    minWidth: 180,
  },
  annualRecapError: {
    color: theme.ui.danger,
    ...theme.typography.bodySm,
    fontWeight: '800',
  },
  modalBackdrop: {
    flex: 1,
    justifyContent: 'center',
    padding: theme.spacing.lg,
    backgroundColor: alpha(theme.ui.bg.app, 0.78),
  },
  modalCard: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.card,
    backgroundColor: theme.ui.bg.card,
    padding: theme.spacing.lg,
    gap: theme.spacing.md,
    ...theme.shadow.lg,
  },
  modalTitle: {
    color: theme.ui.text.onDark,
    ...theme.typography.headingSm,
    fontWeight: '900',
  },
  modalText: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  modalActions: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  modalSecondaryButton: {
    flex: 1,
    minHeight: 52,
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.ui.bg.cardRaised,
    paddingHorizontal: theme.spacing.md,
  },
  modalSecondaryText: {
    color: theme.ui.text.onDark,
    ...theme.typography.label,
    fontWeight: '800',
    textAlign: 'center',
  },
  modalPrimaryButton: {
    flex: 1,
    minHeight: 52,
  },
});

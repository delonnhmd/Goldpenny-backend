import React, { useEffect, useMemo, useState } from 'react';
import { router, usePathname } from 'expo-router';
import { LayoutChangeEvent, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { PlayerStatusBar } from '@/components/gameMap';
import { OnboardingStepOverlay } from '@/components/onboarding';
import AppShell from '@/components/layout/AppShell';
import { gameplayBottomNavBlueprint } from '@/components/layout/AppBottomNav';
import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import FadeInView from '@/components/motion/FadeInView';
import ErrorStateView from '@/components/ui/ErrorStateView';
import LoadingSkeleton from '@/components/ui/LoadingSkeleton';
import SectionCard from '@/components/ui/SectionCard';
import TextButton from '@/components/ui/TextButton';
import { useOnboarding } from '@/features/onboarding';
import { OnboardingRouteKey } from '@/features/onboarding/context';
import { FeedbackSheet, IssueReportSheet, SoftLaunchGate, useSoftLaunch } from '@/features/softLaunch';
import { theme } from '@/design/theme';
import { recordInfo, recordWarning } from '@/lib/logger';

import { useGameplayLoop } from './context';
import {
  GameplayOpportunityCallout,
  GameplayWarningBanner,
} from './components/GameplayUIParts';
import { PlaytestObserver } from './components/PlaytestObserver';

function sourceLabel(mode: 'live' | 'mixed' | 'mock'): string {
  if (mode === 'mock') return 'Mock Data Mode';
  if (mode === 'mixed') return 'Mixed Data Mode';
  return 'Live Data Mode';
}

function sourceCopy(mode: 'live' | 'mixed' | 'mock'): string {
  if (mode === 'mock') {
    return 'Backend is unavailable right now. Local mock data is active so the gameplay loop remains playable.';
  }
  if (mode === 'mixed') {
    return 'Some sections are using local fallback data while backend endpoints recover.';
  }
  return 'Connected to backend source of truth.';
}

const INTERACTION_DIAGNOSTICS_ENABLED =
  __DEV__
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

const PAGE_IDENTITY: Record<string, { eyebrow: string; mood: string; chips: string[] }> = {
  brief: {
    eyebrow: 'Daily intelligence',
    mood: 'Signals, narrative, and settlement pressure in one premium brief.',
    chips: ['City signals', 'Narrative', 'Settle day'],
  },
  dashboard: {
    eyebrow: 'Command center',
    mood: 'Personal cash, pressure, timing, and choices presented like a live game HUD.',
    chips: ['Cash flow', 'Health', 'Pressure'],
  },
  work: {
    eyebrow: 'Career lane',
    mood: 'Shifts, wage growth, certifications, and progression should feel like upward momentum.',
    chips: ['Shift window', 'XP path', 'Income'],
  },
  business: {
    eyebrow: 'Asset lane',
    mood: 'Your business screen tracks growth, margin, staffing, and execution risk like a management game.',
    chips: ['Revenue', 'Margin', 'Operations'],
  },
  market: {
    eyebrow: 'Market lane',
    mood: 'Basket signals and stock exposure feel like readable opportunity, not spreadsheet output.',
    chips: ['Baskets', 'Volatility', 'Capital'],
  },
  life: {
    eyebrow: 'Routine lane',
    mood: 'Housing, meals, stress, and emergency cash now read like survival choices inside the city.',
    chips: ['Meals', 'Housing', 'Recovery'],
  },
  summary: {
    eyebrow: 'Closeout',
    mood: 'End-of-day outcomes, consequences, and next-day reset should land with clarity.',
    chips: ['Results', 'Carryover', 'Reset'],
  },
};

export default function GameplayLoopScaffold({
  title,
  subtitle,
  activeNavKey,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  activeNavKey: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const softLaunch = useSoftLaunch();
  const pathname = usePathname();
  const [showIssueReport, setShowIssueReport] = useState(false);
  const [measuredContentHeight, setMeasuredContentHeight] = useState<number | null>(null);

  // Dev bypass: EXPO_PUBLIC_SOFT_LAUNCH_BYPASS=true skips the gate entirely.
  const bypassGate =
    process.env.EXPO_PUBLIC_SOFT_LAUNCH_BYPASS === 'true' ||
    process.env.EXPO_PUBLIC_SOFT_LAUNCH_BYPASS === '1';

  const gateBlocked = !bypassGate && !softLaunch.isLoading && !softLaunch.isMember;

  const {
    currentStep: onboardingStep,
    ensureRoute,
    expectedRoute,
    isActive: onboardingActive,
    isSimplifiedMode,
    navigateTo,
  } = onboarding;
  const degradedSections = Array.isArray(loop.dashboard?.debug_meta?.degraded_sections)
    ? (loop.dashboard?.debug_meta?.degraded_sections as string[])
    : [];
  const economyModuleDegraded = degradedSections.includes('economy')
    || loop.sourceNotes.some((note) => String(note || '').toLowerCase().startsWith('economy_summary:'));
  const errorText = String(loop.error || '');
  const economyOnlyFailure = errorText.toLowerCase().includes('basket pricing');
  const stats = loop.dashboard?.stats;
  const identity = PAGE_IDENTITY[activeNavKey] || {
    eyebrow: 'Gold Penny',
    mood: subtitle,
    chips: ['Gameplay'],
  };

  useEffect(() => {
    ensureRoute(activeNavKey as OnboardingRouteKey);
  }, [activeNavKey, ensureRoute]);

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Gameplay loop route changed.', {
      action: 'route_change',
      context: {
        playerId: loop.playerId,
        pathname,
        activeNavKey,
      },
    });
  }, [activeNavKey, loop.playerId, pathname]);

  useEffect(() => {
    const targetDay = loop.summaryAutoOpenDay;
    if (!targetDay) return;

    if (activeNavKey === 'summary') {
      loop.consumeSummaryAutoOpen();
      return;
    }

    if (onboardingActive && expectedRoute && expectedRoute !== 'summary') {
      if (INTERACTION_DIAGNOSTICS_ENABLED) {
        recordWarning('gameplayLoop', 'Auto summary navigation blocked by onboarding route guard.', {
          action: 'summary_auto_nav_blocked',
          context: {
            playerId: loop.playerId,
            targetDay,
            activeNavKey,
            expectedRoute,
          },
        });
      }
      return;
    }

    const allowed = navigateTo('summary');
    if (INTERACTION_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayLoop', 'Auto summary navigation evaluated.', {
        action: 'summary_auto_nav',
        context: {
          playerId: loop.playerId,
          targetDay,
          allowed,
          fromRoute: activeNavKey,
        },
      });
    }
    if (allowed) {
      loop.consumeSummaryAutoOpen();
    }
  }, [
    activeNavKey,
    expectedRoute,
    loop,
    navigateTo,
    onboardingActive,
  ]);

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Gameplay screen content diagnostics.', {
      action: 'screen_content_mount',
      context: {
        playerId: loop.playerId,
        screen: activeNavKey,
        hasBundle: Boolean(loop.bundle),
        hasDashboard: Boolean(loop.dashboard),
        hasActionHub: Boolean(loop.actionHub),
        hasEconomySummary: Boolean(loop.economySummary),
        hasStockMarket: Boolean(loop.stockMarket),
        hasBusinesses: Boolean(loop.businesses),
        hasEndOfDaySummary: Boolean(loop.endOfDaySummary),
        animationWrapperMode: 'native_safe_plain',
        fallbackPlainContainer: true,
        measuredContentHeight,
      },
    });
  }, [
    activeNavKey,
    loop.actionHub,
    loop.bundle,
    loop.businesses,
    loop.dashboard,
    loop.economySummary,
    loop.endOfDaySummary,
    loop.playerId,
    loop.stockMarket,
    measuredContentHeight,
  ]);

  const handleContentLayout = (event: LayoutChangeEvent) => {
    const nextHeight = Math.round(event.nativeEvent.layout.height || 0);
    if (!nextHeight) return;
    if (nextHeight === measuredContentHeight) return;
    setMeasuredContentHeight(nextHeight);
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Gameplay content layout measured.', {
      action: 'content_layout',
      context: {
        playerId: loop.playerId,
        screen: activeNavKey,
        measuredContentHeight: nextHeight,
      },
    });
  };

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Onboarding overlay state changed.', {
      action: 'onboarding_overlay',
      context: {
        playerId: loop.playerId,
        onboardingActive,
        stepKey: onboardingStep?.key || null,
        expectedRoute: expectedRoute || null,
      },
    });
  }, [expectedRoute, onboardingActive, onboardingStep?.key, loop.playerId]);

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Soft launch gate state changed.', {
      action: 'soft_launch_gate',
      context: {
        playerId: loop.playerId,
        gateBlocked,
        bypassGate,
        isMember: softLaunch.isMember,
        isLoading: softLaunch.isLoading,
      },
    });
  }, [bypassGate, gateBlocked, loop.playerId, softLaunch.isLoading, softLaunch.isMember]);

  const bottomNavItems = useMemo(
    () => gameplayBottomNavBlueprint
      .filter((item) => !(onboardingActive && (item.key === 'business' || item.key === 'map')))
      .map((item) => ({
        ...item,
        onPress: () => {
          if (INTERACTION_DIAGNOSTICS_ENABLED) {
            recordInfo('gameplayLoop', 'Bottom nav pressed.', {
              action: 'tab_press',
              context: {
                playerId: loop.playerId,
                fromRoute: activeNavKey,
                targetRoute: item.key,
                onboardingActive,
                expectedRoute: expectedRoute || null,
              },
            });
          }
          const allowed = navigateTo(item.key as OnboardingRouteKey);
          if (!allowed && INTERACTION_DIAGNOSTICS_ENABLED) {
            recordWarning('gameplayLoop', 'Bottom nav press blocked by onboarding route guard.', {
              action: 'tab_press_blocked',
              context: {
                playerId: loop.playerId,
                fromRoute: activeNavKey,
                targetRoute: item.key,
                expectedRoute: expectedRoute || null,
                onboardingStepKey: onboardingStep?.key || null,
              },
            });
          }
        },
      })),
    [activeNavKey, expectedRoute, navigateTo, onboardingActive, onboardingStep?.key, loop.playerId],
  );

  // ── Soft launch gate ────────────────────────────────────────────────────────
  if (gateBlocked) {
    return (
      <SoftLaunchGate
        onJoin={softLaunch.joinWithCode}
        error={softLaunch.joinError}
        isLoading={softLaunch.isLoading}
      />
    );
  }

  return (
    <AppShell
      title={title}
      subtitle={subtitle}
      headerRight={<TextButton label="Account" onPress={() => router.push('/account')} />}
      topStatusBar={(
        <PlayerStatusBar
          cash={Number(stats?.cash_xgp ?? 0)}
          stress={Number(stats?.stress ?? 0)}
          health={Number(stats?.health ?? 100)}
          dayNumber={Number(loop.authoritativeState?.day_number ?? 1)}
        />
      )}
      bottomNavItems={bottomNavItems}
      activeBottomNavKey={activeNavKey}
      footer={footer}
    >
      <PageContainer>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
          refreshControl={(
            <RefreshControl
              refreshing={loop.refreshing}
              onRefresh={() => {
                void loop.refresh();
              }}
            />
          )}
        >
          <ContentStack gap={theme.spacing.md} onLayout={handleContentLayout}>
            <FadeInView style={styles.pageHero}>
              <View style={styles.pageHeroCard}>
                <Text style={styles.pageHeroEyebrow}>{identity.eyebrow}</Text>
                <Text style={styles.pageHeroTitle}>{title}</Text>
                <Text style={styles.pageHeroBody}>{identity.mood}</Text>
                <View style={styles.heroChipRow}>
                  {identity.chips.map((chip) => (
                    <View key={chip} style={styles.heroChip}>
                      <Text style={styles.heroChipText}>{chip}</Text>
                    </View>
                  ))}
                </View>
              </View>
            </FadeInView>
            <PlaytestObserver />
            {onboardingActive ? <OnboardingStepOverlay /> : null}

            {!isSimplifiedMode && loop.sourceMode !== 'live' ? (
              <GameplayWarningBanner
                title={sourceLabel(loop.sourceMode)}
                message={sourceCopy(loop.sourceMode)}
                tone={loop.sourceMode === 'mixed' ? 'warning' : 'info'}
              />
            ) : null}

            {loop.feedback ? (
              loop.feedback.tone === 'success' ? (
                <GameplayOpportunityCallout title="Action Update" message={loop.feedback.message} />
              ) : (
                <GameplayWarningBanner
                  title={loop.feedback.tone === 'error' ? 'Needs Attention' : 'Gameplay Note'}
                  message={loop.feedback.message}
                  tone={loop.feedback.tone === 'error' ? 'danger' : 'info'}
                />
              )
            ) : null}

            {economyModuleDegraded ? (
              <GameplayWarningBanner
                title="Economy module temporarily unavailable"
                message="Dashboard partially loaded. Work and core actions remain available."
                tone="warning"
              />
            ) : null}

            {loop.error && !loop.bundle ? (
              <ErrorStateView
                title={economyOnlyFailure ? 'Economy module temporarily unavailable' : 'Gameplay loop unavailable'}
                message={
                  economyOnlyFailure
                    ? 'Dashboard partially loaded. Work and core actions remain available. Retry when economy data recovers.'
                    : loop.error
                }
                onRetry={() => {
                  void loop.refresh();
                }}
              />
            ) : null}

            {!loop.bundle && loop.loading ? (
              <SectionCard
                title="Loading gameplay loop"
                summary="Syncing dashboard, economy, market, and business state."
              >
                <LoadingSkeleton lines={4} />
              </SectionCard>
            ) : (
              <FadeInView delay={40}>
                {children}
              </FadeInView>
            )}
          </ContentStack>
        </ScrollView>
      </PageContainer>

      {/* Soft launch feedback sheet — shown after Day 1/2 settlement */}
      <FeedbackSheet
        visible={loop.feedbackPromptDay !== null}
        gameDay={loop.feedbackPromptDay ?? 1}
        onSubmit={(payload) => softLaunch.submitFeedback(payload)}
        onDismiss={loop.dismissFeedbackPrompt}
      />

      {/* Issue report sheet — shown on demand */}
      <IssueReportSheet
        visible={showIssueReport}
        onSubmit={(payload) => softLaunch.submitIssue(payload)}
        onDismiss={() => setShowIssueReport(false)}
      />
    </AppShell>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xxxl,
  },
  pageHero: {
    width: '100%',
  },
  pageHeroCard: {
    borderRadius: theme.radius.xl,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.lg,
    backgroundColor: theme.ui.bg.card,
    borderWidth: 1,
    borderColor: theme.ui.border,
    gap: theme.spacing.sm,
    ...theme.shadow.md,
  },
  pageHeroEyebrow: {
    ...theme.typography.caption,
    color: theme.ui.info,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '800',
  },
  pageHeroTitle: {
    ...theme.typography.headingLg,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  pageHeroBody: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  heroChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  heroChip: {
    borderRadius: theme.radius.pill,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    backgroundColor: theme.ui.bg.cardRaised,
    borderWidth: 1,
    borderColor: theme.ui.border,
  },
  heroChipText: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
});

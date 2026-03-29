import React, { useEffect, useMemo, useState } from 'react';
import { usePathname } from 'expo-router';
import { LayoutChangeEvent, RefreshControl, ScrollView, StyleSheet } from 'react-native';

import { OnboardingStepOverlay } from '@/components/onboarding';
import AppShell from '@/components/layout/AppShell';
import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import ErrorStateView from '@/components/ui/ErrorStateView';
import LoadingSkeleton from '@/components/ui/LoadingSkeleton';
import SectionCard from '@/components/ui/SectionCard';
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
  const sourceTone = loop.sourceMode === 'live' ? 'positive' : loop.sourceMode === 'mixed' ? 'warning' : 'info';

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
    () => ([
      { key: 'brief', label: 'Brief' },
      { key: 'dashboard', label: 'Dashboard' },
      { key: 'market', label: 'Market' },
      { key: 'business', label: 'Business' },
    ]
      .filter((item) => !(onboardingActive && item.key === 'business'))
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
      }))),
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

            {loop.error && !loop.bundle ? (
              <ErrorStateView
                title="Gameplay loop unavailable"
                message={loop.error}
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
              children
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
});

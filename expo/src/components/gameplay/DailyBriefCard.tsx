import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';

import HighlightOnChangeView from '@/components/motion/HighlightOnChangeView';
import SlideFadeInOnChange from '@/components/motion/SlideFadeInOnChange';
import { alpha, theme } from '@/design/theme';
import {
  PlayerDashboardResponse,
  StrategicAlert,
  StrategicBrief,
  StrategicRecommendedAction,
  StrategicTargetScreen,
} from '@/types/gameplay';

function targetScreenToRoute(playerId: string | undefined, target: StrategicTargetScreen): string | null {
  if (!playerId) return null;
  switch (target) {
    case 'Life':
      return `/gameplay/loop/${playerId}/life`;
    case 'Work':
      return `/gameplay/loop/${playerId}/work`;
    case 'Business':
      return `/gameplay/loop/${playerId}/business`;
    case 'Map':
      return `/gameplay/loop/${playerId}/map`;
    case 'Portfolio':
      return `/gameplay/loop/${playerId}/market`;
    case 'Summary':
      return `/gameplay/loop/${playerId}/summary`;
    default:
      return null;
  }
}

function firstMeaningfulLine(value: string | null | undefined): string {
  return String(value || '')
    .split(/(?<=[.!?])\s+/)
    .map((entry) => entry.trim())
    .find(Boolean) || 'No summary available.';
}

function severityColor(severity: string): string {
  if (severity === 'high') return theme.ui.danger;
  if (severity === 'medium') return theme.ui.warning;
  return theme.ui.info;
}

function pickTopRisk(brief: StrategicBrief | null | undefined): StrategicAlert | null {
  if (!brief) return null;
  return brief.risk_warnings?.[0] ?? null;
}

function pickTopBusiness(brief: StrategicBrief | null | undefined): StrategicAlert | null {
  if (!brief) return null;
  return brief.business_alerts?.[0] ?? null;
}

function pickTopPortfolio(brief: StrategicBrief | null | undefined): StrategicAlert | null {
  if (!brief) return null;
  return brief.portfolio_alerts?.[0] ?? null;
}

export default function DailyBriefCard({
  dashboard,
  impactBullets = [],
  dayKey,
}: {
  dashboard: PlayerDashboardResponse;
  impactBullets?: string[];
  dayKey?: string | number;
}) {
  const summary = firstMeaningfulLine(dashboard.daily_brief);
  const heroWatchValue = `${dashboard.headline || ''}|${summary}`;
  const revealKey = `${String(dayKey ?? '')}|${heroWatchValue}`;
  const visibleBullets = impactBullets.filter((entry) => String(entry || '').trim()).slice(0, 3);

  const strategic = dashboard.strategic_brief ?? null;
  const topRisk = pickTopRisk(strategic);
  const topBusiness = pickTopBusiness(strategic);
  const topPortfolio = pickTopPortfolio(strategic);
  const topActions: StrategicRecommendedAction[] = (strategic?.recommended_actions ?? []).slice(0, 3);
  const todayPressure = strategic?.today_pressure || '';

  return (
    <View style={styles.card}>
      <HighlightOnChangeView watchValue={heroWatchValue} style={styles.heroBlock}>
        <SlideFadeInOnChange watchValue={`${revealKey}_headline`} delayMs={0}>
          <Text style={styles.headerLabel}>Daily Brief</Text>
          <Text style={styles.headline}>{dashboard.headline || 'Today at Gold Penny'}</Text>
        </SlideFadeInOnChange>
        <SlideFadeInOnChange watchValue={`${revealKey}_summary`} delayMs={100}>
          <Text style={styles.summary}>{summary}</Text>
        </SlideFadeInOnChange>
        {visibleBullets.length > 0 ? (
          <SlideFadeInOnChange watchValue={`${revealKey}_macro`} delayMs={200}>
            <View style={styles.bulletList}>
              {visibleBullets.map((entry) => (
                <Text key={entry} style={styles.bulletItem}>
                  {'- '}
                  {entry}
                </Text>
              ))}
            </View>
          </SlideFadeInOnChange>
        ) : null}
      </HighlightOnChangeView>

      {strategic ? (
        <View style={styles.strategicBlock}>
          {todayPressure ? (
            <View style={styles.row}>
              <Text style={styles.rowLabel}>Today's Pressure</Text>
              <Text style={styles.rowValue}>{todayPressure}</Text>
            </View>
          ) : null}
          {topRisk ? (
            <View style={styles.row}>
              <Text style={[styles.rowLabel, { color: severityColor(topRisk.severity) }]}>Top Risk</Text>
              <Text style={styles.rowValue} numberOfLines={2}>
                {topRisk.cause}
              </Text>
            </View>
          ) : null}
          {topBusiness ? (
            <View style={styles.row}>
              <Text style={[styles.rowLabel, { color: severityColor(topBusiness.severity) }]}>
                Business Alert
              </Text>
              <Text style={styles.rowValue} numberOfLines={2}>
                {topBusiness.cause}
              </Text>
            </View>
          ) : null}
          {topPortfolio ? (
            <View style={styles.row}>
              <Text style={[styles.rowLabel, { color: severityColor(topPortfolio.severity) }]}>
                Portfolio Alert
              </Text>
              <Text style={styles.rowValue} numberOfLines={2}>
                {topPortfolio.cause}
              </Text>
            </View>
          ) : null}
          {topActions.length > 0 ? (
            <View style={styles.actionsBlock}>
              <Text style={styles.actionsLabel}>Recommended Actions</Text>
              {topActions.map((action, index) => {
                const route = targetScreenToRoute(dashboard.player_id, action.target_screen);
                return (
                  <Pressable
                    key={`${action.action}-${index}`}
                    onPress={() => {
                      if (route) router.push(route as never);
                    }}
                    accessibilityRole="button"
                    accessibilityLabel={action.action}
                  >
                    <Text style={styles.actionItem}>
                      {`${index + 1}. ${action.action}`}
                      <Text style={styles.actionTarget}>{` (${action.target_screen})`}</Text>
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: alpha(theme.ui.info, 0.18),
    borderRadius: theme.radius.xl,
    backgroundColor: theme.ui.bg.card,
    padding: theme.spacing.lg,
    ...theme.shadow.md,
  },
  heroBlock: {
    gap: theme.spacing.xs,
  },
  headerLabel: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    color: theme.ui.info,
    fontWeight: '800',
  },
  headline: {
    ...theme.typography.headingLg,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  summary: {
    color: theme.color.textSecondary,
    ...theme.typography.bodyMd,
    lineHeight: 20,
  },
  bulletList: {
    gap: theme.spacing.xxs,
    paddingTop: theme.spacing.xs,
  },
  bulletItem: {
    color: theme.ui.text.onLightMuted,
    ...theme.typography.bodySm,
    lineHeight: 18,
  },
  strategicBlock: {
    marginTop: theme.spacing.md,
    paddingTop: theme.spacing.sm,
    borderTopWidth: 1,
    borderTopColor: alpha(theme.ui.info, 0.12),
    gap: theme.spacing.xs,
  },
  row: {
    gap: 2,
  },
  rowLabel: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    color: theme.ui.info,
    fontWeight: '700',
  },
  rowValue: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    lineHeight: 18,
  },
  actionsBlock: {
    marginTop: theme.spacing.xs,
    gap: 2,
  },
  actionsLabel: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  actionItem: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    lineHeight: 18,
  },
  actionTarget: {
    color: theme.ui.text.onLightMuted,
    fontWeight: '600',
  },
});

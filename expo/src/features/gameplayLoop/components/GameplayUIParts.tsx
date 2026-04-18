import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import BottomActionBar from '@/components/layout/BottomActionBar';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import SurfaceCard from '@/components/ui/SurfaceCard';
import { theme } from '@/design/theme';

export type GameplayTone = 'neutral' | 'positive' | 'warning' | 'danger' | 'info';

interface TonePalette {
  background: string;
  border: string;
  text: string;
}

const tonePalette: Record<GameplayTone, TonePalette> = {
  neutral: {
    background: theme.color.surfaceAlt,
    border: 'rgba(148, 163, 184, 0.16)',
    text: theme.color.textPrimary,
  },
  positive: {
    background: 'rgba(20, 83, 45, 0.38)',
    border: 'rgba(74, 222, 128, 0.28)',
    text: '#86efac',
  },
  warning: {
    background: 'rgba(120, 53, 15, 0.34)',
    border: 'rgba(251, 191, 36, 0.28)',
    text: '#fcd34d',
  },
  danger: {
    background: 'rgba(127, 29, 29, 0.34)',
    border: 'rgba(248, 113, 113, 0.28)',
    text: '#fca5a5',
  },
  info: {
    background: 'rgba(30, 64, 175, 0.28)',
    border: 'rgba(96, 165, 250, 0.28)',
    text: '#93c5fd',
  },
};

function paletteFor(tone: GameplayTone): TonePalette {
  return tonePalette[tone] || tonePalette.neutral;
}

export function toneFromSignedValue(value: number): GameplayTone {
  if (value > 0) return 'positive';
  if (value < 0) return 'danger';
  return 'neutral';
}

export function GameplaySectionHeader({
  title,
  subtitle,
  eyebrow,
  right,
}: {
  title: string;
  subtitle?: string | null;
  eyebrow?: string | null;
  right?: React.ReactNode;
}) {
  return (
    <View style={styles.sectionHeaderRow}>
      <View style={styles.sectionHeaderCopy}>
        {eyebrow ? <Text style={styles.sectionEyebrow}>{eyebrow}</Text> : null}
        <Text style={styles.sectionTitle}>{title}</Text>
        {subtitle ? <Text style={styles.sectionSubtitle}>{subtitle}</Text> : null}
      </View>
      {right ? <View style={styles.sectionHeaderRight}>{right}</View> : null}
    </View>
  );
}

export function GameplaySummaryCard({
  title,
  subtitle,
  eyebrow,
  right,
  children,
}: {
  title: string;
  subtitle?: string | null;
  eyebrow?: string | null;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <SurfaceCard style={styles.summaryCard}>
      <GameplaySectionHeader title={title} subtitle={subtitle} eyebrow={eyebrow} right={right} />
      <View style={styles.summaryBody}>{children}</View>
    </SurfaceCard>
  );
}

export function GameplayStatCard({
  label,
  value,
  note,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  note?: string | null;
  tone?: GameplayTone;
}) {
  const palette = paletteFor(tone);
  return (
    <View style={[styles.statCard, { borderColor: palette.border, backgroundColor: palette.background }]}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, { color: palette.text }]} numberOfLines={2}>{value}</Text>
      {note ? <Text style={styles.statNote} numberOfLines={2}>{note}</Text> : null}
    </View>
  );
}

export function GameplayTrendChip({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  tone?: GameplayTone;
}) {
  const palette = paletteFor(tone);
  return (
    <View style={[styles.trendChip, { borderColor: palette.border, backgroundColor: palette.background }]}>
      <Text style={styles.trendLabel}>{label}</Text>
      <Text style={[styles.trendValue, { color: palette.text }]} numberOfLines={1}>{value}</Text>
    </View>
  );
}

export function GameplayCompactMetricRows({
  items,
}: {
  items: Array<{ label: string; value: string; tone?: GameplayTone; valueNode?: React.ReactNode }>;
}) {
  return (
    <View style={styles.metricRows}>
      {items.map((item, index) => (
        <View key={`${item.label}_${index}`} style={styles.metricRow}>
          <Text style={styles.metricLabel}>{item.label}</Text>
          {item.valueNode ? (
            <View style={styles.metricValueNode}>
              {item.valueNode}
            </View>
          ) : (
            <Text
              style={[
                styles.metricValue,
                item.tone ? { color: paletteFor(item.tone).text } : null,
              ]}
              numberOfLines={2}
            >
              {item.value}
            </Text>
          )}
        </View>
      ))}
    </View>
  );
}

export function GameplayWarningBanner({
  title,
  message,
  tone = 'warning',
}: {
  title: string;
  message: string;
  tone?: Exclude<GameplayTone, 'positive' | 'neutral'>;
}) {
  const palette = paletteFor(tone);
  return (
    <View style={[styles.banner, { borderColor: palette.border, backgroundColor: palette.background }]}>
      <Text style={[styles.bannerTitle, { color: palette.text }]}>{title}</Text>
      <Text style={[styles.bannerMessage, { color: palette.text }]}>{message}</Text>
    </View>
  );
}

export function GameplayOpportunityCallout({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <View style={styles.opportunityCallout}>
      <Text style={styles.opportunityTitle}>{title}</Text>
      <Text style={styles.opportunityText}>{message}</Text>
    </View>
  );
}

export function GameplayStickyActionArea({
  summary,
  primaryLabel,
  onPrimaryPress,
  primaryDisabled,
  primaryLoading,
  secondaryLabel,
  onSecondaryPress,
  secondaryDisabled,
}: {
  summary?: string | null;
  primaryLabel: string;
  onPrimaryPress?: () => void;
  primaryDisabled?: boolean;
  primaryLoading?: boolean;
  secondaryLabel?: string;
  onSecondaryPress?: () => void;
  secondaryDisabled?: boolean;
}) {
  return (
    <BottomActionBar>
      {summary ? <Text style={styles.stickySummary}>{summary}</Text> : null}
      <View style={styles.stickyButtonRow}>
        {secondaryLabel ? (
          <SecondaryButton
            label={secondaryLabel}
            onPress={onSecondaryPress}
            disabled={secondaryDisabled}
            style={styles.stickyButton}
          />
        ) : null}
        <PrimaryButton
          label={primaryLabel}
          onPress={onPrimaryPress}
          disabled={primaryDisabled}
          loading={primaryLoading}
          style={styles.stickyButton}
        />
      </View>
    </BottomActionBar>
  );
}

const styles = StyleSheet.create({
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  sectionHeaderCopy: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  sectionHeaderRight: {
    alignItems: 'flex-end',
  },
  sectionEyebrow: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.7,
    fontWeight: '800',
    color: '#67e8f9',
  },
  sectionTitle: {
    ...theme.typography.headingMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  sectionSubtitle: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  summaryCard: {
    gap: theme.spacing.md,
  },
  summaryBody: {
    gap: theme.spacing.sm,
  },
  statCard: {
    flex: 1,
    minWidth: 130,
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    gap: theme.spacing.xxs,
  },
  statLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  statValue: {
    ...theme.typography.headingSm,
    fontWeight: '800',
    color: theme.color.textPrimary,
  },
  statNote: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    lineHeight: 15,
  },
  trendChip: {
    borderWidth: 1,
    borderRadius: theme.radius.pill,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    gap: 1,
    minWidth: 104,
  },
  trendLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  trendValue: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
  metricRows: {
    borderWidth: 1,
    borderColor: 'rgba(148, 163, 184, 0.14)',
    borderRadius: theme.radius.lg,
    backgroundColor: 'rgba(8, 15, 30, 0.76)',
    overflow: 'hidden',
  },
  metricRow: {
    minHeight: 40,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(148, 163, 184, 0.12)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  metricLabel: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
    flex: 1,
  },
  metricValue: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    fontWeight: '700',
    maxWidth: '60%',
    textAlign: 'right',
  },
  metricValueNode: {
    maxWidth: '60%',
    alignItems: 'flex-end',
    justifyContent: 'center',
  },
  banner: {
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  bannerTitle: {
    ...theme.typography.label,
    fontWeight: '800',
  },
  bannerMessage: {
    ...theme.typography.bodySm,
    fontWeight: '600',
  },
  opportunityCallout: {
    borderWidth: 1,
    borderColor: 'rgba(74, 222, 128, 0.3)',
    borderRadius: theme.radius.lg,
    backgroundColor: 'rgba(20, 83, 45, 0.34)',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  opportunityTitle: {
    ...theme.typography.label,
    color: '#86efac',
    fontWeight: '800',
  },
  opportunityText: {
    ...theme.typography.bodySm,
    color: '#dcfce7',
    fontWeight: '600',
  },
  stickySummary: {
    ...theme.typography.bodySm,
    color: '#a8b6c9',
  },
  stickyButtonRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  stickyButton: {
    flex: 1,
    minWidth: 144,
  },
});

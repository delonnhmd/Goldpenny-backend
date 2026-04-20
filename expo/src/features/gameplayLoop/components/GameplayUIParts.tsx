import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import BottomActionBar from '@/components/layout/BottomActionBar';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import SurfaceCard from '@/components/ui/SurfaceCard';
import { alpha, theme } from '@/design/theme';

export type GameplayTone = 'neutral' | 'positive' | 'warning' | 'danger' | 'info';

interface TonePalette {
  background: string;
  border: string;
  text: string;
}

const tonePalette: Record<GameplayTone, TonePalette> = {
  neutral: {
    background: '#F9FAFB',
    border: theme.gameUi.cardBorder,
    text: theme.gameUi.textPrimary,
  },
  positive: {
    background: alpha(theme.gameUi.success, 0.1),
    border: alpha(theme.gameUi.success, 0.28),
    text: theme.gameUi.success,
  },
  warning: {
    background: alpha(theme.gameUi.warning, 0.1),
    border: alpha(theme.gameUi.warning, 0.28),
    text: theme.gameUi.warning,
  },
  danger: {
    background: alpha(theme.gameUi.danger, 0.1),
    border: alpha(theme.gameUi.danger, 0.28),
    text: theme.gameUi.danger,
  },
  info: {
    background: alpha(theme.gameUi.primary, 0.1),
    border: alpha(theme.gameUi.primary, 0.28),
    text: theme.gameUi.primary,
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
  items: { label: string; value: string; tone?: GameplayTone; valueNode?: React.ReactNode }[];
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
    color: theme.gameUi.primary,
  },
  sectionTitle: {
    ...theme.typography.headingMd,
    color: theme.gameUi.textPrimary,
    fontWeight: '800',
  },
  sectionSubtitle: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textSecondary,
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
    color: theme.gameUi.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  statValue: {
    ...theme.typography.headingSm,
    fontWeight: '800',
    color: theme.gameUi.textPrimary,
  },
  statNote: {
    ...theme.typography.caption,
    color: theme.gameUi.textSecondary,
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
    color: theme.gameUi.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  trendValue: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textPrimary,
    fontWeight: '700',
  },
  metricRows: {
    borderWidth: 1,
    borderColor: theme.gameUi.cardBorder,
    borderRadius: theme.radius.lg,
    backgroundColor: '#F9FAFB',
    overflow: 'hidden',
  },
  metricRow: {
    minHeight: 40,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: theme.gameUi.cardBorder,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  metricLabel: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textSecondary,
    flex: 1,
  },
  metricValue: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textPrimary,
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
    borderColor: alpha(theme.gameUi.success, 0.3),
    borderRadius: theme.radius.lg,
    backgroundColor: alpha(theme.gameUi.success, 0.1),
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  opportunityTitle: {
    ...theme.typography.label,
    color: theme.gameUi.success,
    fontWeight: '800',
  },
  opportunityText: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textPrimary,
    fontWeight: '600',
  },
  stickySummary: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textSecondary,
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

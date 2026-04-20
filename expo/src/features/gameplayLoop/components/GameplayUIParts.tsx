import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import BottomActionBar from '@/components/layout/BottomActionBar';
import Card, { CardVariant } from '@/components/ui/Card';
import Chip, { ChipVariant } from '@/components/ui/Chip';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';

export type GameplayTone = 'neutral' | 'positive' | 'warning' | 'danger' | 'info';

interface TonePalette {
  cardVariant: CardVariant;
  chipVariant: ChipVariant;
  text: string;
}

const tonePalette: Record<GameplayTone, TonePalette> = {
  neutral: {
    cardVariant: 'default',
    chipVariant: 'neutral',
    text: theme.ui.text.onDark,
  },
  positive: {
    cardVariant: 'positive',
    chipVariant: 'positive',
    text: theme.ui.positive,
  },
  warning: {
    cardVariant: 'warning',
    chipVariant: 'warning',
    text: theme.ui.warning,
  },
  danger: {
    cardVariant: 'danger',
    chipVariant: 'danger',
    text: theme.ui.danger,
  },
  info: {
    cardVariant: 'info',
    chipVariant: 'info',
    text: theme.ui.info,
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
    <Card style={styles.summaryCard}>
      <GameplaySectionHeader title={title} subtitle={subtitle} eyebrow={eyebrow} right={right} />
      <View style={styles.summaryBody}>{children}</View>
    </Card>
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
    <Card variant={palette.cardVariant} style={styles.statCard}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, { color: palette.text }]} numberOfLines={2}>{value}</Text>
      {note ? <Text style={styles.statNote} numberOfLines={2}>{note}</Text> : null}
    </Card>
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
  return <Chip label={`${label}: ${value}`} variant={palette.chipVariant} />;
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
    <Card variant={palette.cardVariant} style={styles.banner}>
      <Text style={[styles.bannerTitle, { color: palette.text }]}>{title}</Text>
      <Text style={styles.bannerMessage}>{message}</Text>
    </Card>
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
    <Card variant="positive" style={styles.opportunityCallout}>
      <Text style={styles.opportunityTitle}>{title}</Text>
      <Text style={styles.opportunityText}>{message}</Text>
    </Card>
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
    color: theme.ui.info,
  },
  sectionTitle: {
    ...theme.typography.headingMd,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  sectionSubtitle: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
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
    gap: theme.spacing.xxs,
  },
  statLabel: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  statValue: {
    ...theme.typography.headingSm,
    fontWeight: '800',
    color: theme.ui.text.onDark,
  },
  statNote: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    lineHeight: 15,
  },
  metricRows: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    overflow: 'hidden',
  },
  metricRow: {
    minHeight: 40,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: theme.ui.border,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  metricLabel: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
    flex: 1,
  },
  metricValue: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDark,
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
    gap: theme.spacing.xxs,
  },
  bannerTitle: {
    ...theme.typography.label,
    fontWeight: '800',
  },
  bannerMessage: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '600',
  },
  opportunityCallout: {
    gap: theme.spacing.xxs,
  },
  opportunityTitle: {
    ...theme.typography.label,
    color: theme.ui.positive,
    fontWeight: '800',
  },
  opportunityText: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDark,
    fontWeight: '600',
  },
  stickySummary: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
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

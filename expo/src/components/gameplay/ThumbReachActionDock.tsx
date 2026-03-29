import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import BottomActionBar from '@/components/layout/BottomActionBar';
import FadeInView from '@/components/motion/FadeInView';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';

type FeedbackTone = 'success' | 'error' | 'info';

interface DockActionButton {
  id: string;
  label: string;
  onPress?: () => void;
  disabled?: boolean;
  loading?: boolean;
  emphasis?: 'primary' | 'secondary';
}

function feedbackColors(tone: FeedbackTone): { borderColor: string; backgroundColor: string; color: string } {
  if (tone === 'success') {
    return { borderColor: '#86efac', backgroundColor: '#f0fdf4', color: '#166534' };
  }
  if (tone === 'error') {
    return { borderColor: '#fecaca', backgroundColor: '#fef2f2', color: '#b91c1c' };
  }
  return { borderColor: '#bfdbfe', backgroundColor: '#eff6ff', color: '#1e40af' };
}

export default function ThumbReachActionDock({
  dayNumber,
  remainingTimeUnits,
  totalTimeUnits,
  sessionStatus,
  feedback,
  highlightedActionId,
  primaryAction,
  advanceAction,
  secondaryActions,
}: {
  dayNumber: number;
  remainingTimeUnits: number;
  totalTimeUnits: number;
  sessionStatus: 'active' | 'ended';
  feedback?: { tone: FeedbackTone; message: string } | null;
  highlightedActionId?: string | null;
  primaryAction: DockActionButton;
  advanceAction: DockActionButton;
  secondaryActions: DockActionButton[];
}) {
  const feedbackStyle = feedback ? feedbackColors(feedback.tone) : null;

  return (
    <BottomActionBar>
      <View style={styles.summaryRow}>
        <View style={styles.summaryBlock}>
          <View style={styles.dayPill}>
            <Text style={styles.dayPillText}>Day {dayNumber}</Text>
          </View>
          <Text style={styles.summaryTitle}>Primary actions</Text>
        </View>
        <Text style={styles.summaryText}>
          {remainingTimeUnits}/{totalTimeUnits} units left • {sessionStatus === 'active' ? 'Act now' : 'Review and restart'}
        </Text>
      </View>

      {feedback && feedbackStyle ? (
        <FadeInView key={`${feedback.tone}:${feedback.message}`} slide={6}>
          <View
            style={[
              styles.feedbackBox,
              {
                borderColor: feedbackStyle.borderColor,
                backgroundColor: feedbackStyle.backgroundColor,
              },
            ]}
          >
            <Text style={[styles.feedbackLabel, { color: feedbackStyle.color }]}>Latest result</Text>
            <Text style={[styles.feedbackText, { color: feedbackStyle.color }]} numberOfLines={3}>
              {feedback.message}
            </Text>
          </View>
        </FadeInView>
      ) : (
        <Text style={styles.hintText}>Read the brief, take one clear move, then close the day.</Text>
      )}

      <Text style={styles.rowLabel}>Main lane</Text>
      <View style={styles.primaryRow}>
        <PrimaryButton
          label={primaryAction.label}
          onPress={primaryAction.onPress}
          disabled={primaryAction.disabled}
          loading={primaryAction.loading}
          style={[
            styles.primaryButton,
            highlightedActionId === primaryAction.id ? styles.highlightedButton : null,
          ]}
        />
        {advanceAction.emphasis === 'primary' ? (
          <PrimaryButton
            label={advanceAction.label}
            onPress={advanceAction.onPress}
            disabled={advanceAction.disabled}
            loading={advanceAction.loading}
            style={[
              styles.primaryButton,
              highlightedActionId === advanceAction.id ? styles.highlightedButton : null,
            ]}
          />
        ) : (
          <SecondaryButton
            label={advanceAction.label}
            onPress={advanceAction.onPress}
            disabled={advanceAction.disabled}
            loading={advanceAction.loading}
            style={[
              styles.primaryButton,
              highlightedActionId === advanceAction.id ? styles.highlightedButton : null,
            ]}
          />
        )}
      </View>

      <Text style={styles.rowLabel}>Quick access</Text>
      <View style={styles.secondaryRow}>
        {secondaryActions.map((action) => (
          action.emphasis === 'primary' ? (
            <PrimaryButton
              key={action.label}
              label={action.label}
              onPress={action.onPress}
              disabled={action.disabled}
              loading={action.loading}
              style={[
                styles.secondaryButton,
                highlightedActionId === action.id ? styles.highlightedButton : null,
              ]}
            />
          ) : (
            <SecondaryButton
              key={action.label}
              label={action.label}
              onPress={action.onPress}
              disabled={action.disabled}
              loading={action.loading}
              style={[
                styles.secondaryButton,
                highlightedActionId === action.id ? styles.highlightedButton : null,
              ]}
            />
          )
        ))}
      </View>
    </BottomActionBar>
  );
}

const styles = StyleSheet.create({
  summaryRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  summaryBlock: {
    gap: theme.spacing.xs,
  },
  dayPill: {
    borderRadius: 999,
    backgroundColor: '#e0ecff',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
    alignSelf: 'flex-start',
  },
  dayPillText: {
    color: '#1d4ed8',
    ...theme.typography.caption,
    fontWeight: '800',
  },
  summaryTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
    fontWeight: '800',
  },
  summaryText: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
    fontWeight: '600',
    flex: 1,
    textAlign: 'right',
  },
  feedbackBox: {
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  feedbackLabel: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.7,
    fontWeight: '800',
  },
  feedbackText: {
    ...theme.typography.bodySm,
    fontWeight: '700',
    lineHeight: 18,
  },
  hintText: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    lineHeight: 16,
  },
  rowLabel: {
    color: theme.color.muted,
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '800',
  },
  primaryRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  primaryButton: {
    flex: 1,
  },
  secondaryRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  secondaryButton: {
    flexGrow: 1,
    flexBasis: '42%',
    minWidth: 92,
  },
  highlightedButton: {
    borderColor: '#1d4ed8',
    borderWidth: 2,
  },
});
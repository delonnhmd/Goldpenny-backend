import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { formatProgress, progressStatusColor, urgencyColor } from '@/lib/gameplayFormatters';
import { DailyGoalItem } from '@/types/progression';

function GoalRow({ goal }: { goal: DailyGoalItem }) {
  const ratio = Math.max(0, Math.min(1, (goal.progress_current || 0) / Math.max(1, goal.progress_target || 1)));
  return (
    <View style={styles.goalRow}>
      <View style={styles.goalHeader}>
        <Text style={styles.goalTitle}>{goal.title}</Text>
        <Text style={[styles.goalStatus, { color: progressStatusColor(goal.status) }]}>{goal.status}</Text>
      </View>
      <Text style={styles.goalDescription}>{goal.description}</Text>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${Math.round(ratio * 100)}%` }]} />
      </View>
      <View style={styles.goalFooter}>
        <Text style={styles.goalMeta}>{formatProgress(goal.progress_current, goal.progress_target)}</Text>
        <Text style={[styles.goalMeta, { color: urgencyColor(goal.urgency) }]}>{goal.urgency}</Text>
      </View>
      <Text style={styles.rewardText}>Reward: {goal.reward_summary || 'Progress marker'}</Text>
    </View>
  );
}

export default function DailyGoalsCard({ goals }: { goals: DailyGoalItem[] }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Daily Goals</Text>
      <Text style={styles.subheading}>Three focused goals to keep momentum today.</Text>
      {goals.length > 0 ? (
        goals.slice(0, 3).map((goal) => <GoalRow key={goal.goal_key} goal={goal} />)
      ) : (
        <Text style={styles.empty}>No daily goals available yet.</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 12,
    backgroundColor: theme.ui.bg.sheet,
    padding: 14,
    gap: 8,
  },
  heading: {
    color: theme.ui.text.onLight,
    fontSize: 17,
    fontWeight: '800',
  },
  subheading: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  goalRow: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 5,
  },
  goalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  goalTitle: {
    color: theme.ui.text.onLight,
    fontSize: 13,
    fontWeight: '700',
    flex: 1,
  },
  goalStatus: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  goalDescription: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  progressTrack: {
    height: 8,
    borderRadius: 999,
    backgroundColor: theme.ui.border,
    overflow: 'hidden',
  },
  progressFill: {
    height: 8,
    borderRadius: 999,
    backgroundColor: theme.ui.action,
  },
  goalFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  goalMeta: {
    color: theme.ui.text.onLightMuted,
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  rewardText: {
    color: theme.ui.action,
    fontSize: 11,
    lineHeight: 15,
  },
  empty: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
  },
});

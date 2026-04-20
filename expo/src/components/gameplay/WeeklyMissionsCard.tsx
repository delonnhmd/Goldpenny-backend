import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { formatProgress, progressStatusColor } from '@/lib/gameplayFormatters';
import { WeeklyMissionItem } from '@/types/progression';

function MissionRow({ mission }: { mission: WeeklyMissionItem }) {
  const ratio = Math.max(
    0,
    Math.min(1, (mission.progress_current || 0) / Math.max(1, mission.progress_target || 1)),
  );
  return (
    <View style={styles.missionRow}>
      <View style={styles.missionTop}>
        <Text style={styles.missionTitle}>{mission.title}</Text>
        <Text style={[styles.missionStatus, { color: progressStatusColor(mission.status) }]}>
          {mission.status}
        </Text>
      </View>
      <Text style={styles.missionDescription}>{mission.description}</Text>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${Math.round(ratio * 100)}%` }]} />
      </View>
      <View style={styles.missionBottom}>
        <Text style={styles.missionMeta}>{formatProgress(mission.progress_current, mission.progress_target)}</Text>
        <Text style={styles.missionMeta}>{mission.category}</Text>
      </View>
      <Text style={styles.missionReward}>Reward: {mission.reward_summary || 'Weekly milestone'}</Text>
    </View>
  );
}

export default function WeeklyMissionsCard({ missions }: { missions: WeeklyMissionItem[] }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Weekly Missions</Text>
      <Text style={styles.subheading}>Challenge window for this week.</Text>
      {missions.length > 0 ? (
        missions.slice(0, 5).map((mission) => <MissionRow key={mission.mission_key} mission={mission} />)
      ) : (
        <Text style={styles.empty}>No weekly missions active.</Text>
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
  missionRow: {
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 5,
  },
  missionTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  missionTitle: {
    color: theme.ui.text.onLight,
    fontSize: 13,
    fontWeight: '700',
    flex: 1,
  },
  missionStatus: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  missionDescription: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  progressTrack: {
    height: 8,
    borderRadius: 999,
    backgroundColor: theme.ui.info,
    overflow: 'hidden',
  },
  progressFill: {
    height: 8,
    borderRadius: 999,
    backgroundColor: theme.ui.action,
  },
  missionBottom: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  missionMeta: {
    color: theme.ui.text.onLightMuted,
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  missionReward: {
    color: theme.ui.action,
    fontSize: 11,
    lineHeight: 15,
  },
  empty: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
  },
});

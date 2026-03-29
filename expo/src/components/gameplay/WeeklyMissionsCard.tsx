import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

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
    borderColor: '#e2e8f0',
    borderRadius: 12,
    backgroundColor: '#ffffff',
    padding: 14,
    gap: 8,
  },
  heading: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  subheading: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 17,
  },
  missionRow: {
    borderWidth: 1,
    borderColor: '#dbeafe',
    borderRadius: 10,
    backgroundColor: '#eff6ff',
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
    color: '#0f172a',
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
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  progressTrack: {
    height: 8,
    borderRadius: 999,
    backgroundColor: '#bfdbfe',
    overflow: 'hidden',
  },
  progressFill: {
    height: 8,
    borderRadius: 999,
    backgroundColor: '#1d4ed8',
  },
  missionBottom: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  missionMeta: {
    color: '#334155',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  missionReward: {
    color: '#1e3a8a',
    fontSize: 11,
    lineHeight: 15,
  },
  empty: {
    color: '#64748b',
    fontSize: 12,
  },
});

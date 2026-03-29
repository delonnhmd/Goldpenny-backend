import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { statusBadgeColor } from '@/lib/commitmentFormatters';
import { ActiveCommitmentResponse, AvailableCommitmentItem, AvailableCommitmentsResponse } from '@/types/commitment';

export default function CommitmentPickerCard({
  available,
  activeCommitment,
  busy = false,
  onActivate,
}: {
  available: AvailableCommitmentsResponse;
  activeCommitment?: ActiveCommitmentResponse | null;
  busy?: boolean;
  onActivate: (item: AvailableCommitmentItem, options?: { replaceActive?: boolean }) => void;
}) {
  const hasActive = activeCommitment?.status === 'active' && Boolean(activeCommitment.commitment_key);
  const title = hasActive ? 'Switch Commitment' : 'Choose a 3-7 Day Commitment';
  const subtitle = hasActive
    ? `Active now: ${activeCommitment?.title}. Switching will close the current commitment.`
    : 'Pick one plan to track follow-through and momentum over several days.';

  return (
    <View style={styles.card}>
      <Text style={styles.heading}>{title}</Text>
      <Text style={styles.subheading}>{subtitle}</Text>

      {hasActive ? (
        <View style={styles.activeChip}>
          <Text style={[styles.activeChipText, { color: statusBadgeColor(activeCommitment?.status || 'active') }]}>
            ACTIVE: {activeCommitment?.title}
          </Text>
        </View>
      ) : null}

      {available.items.slice(0, 4).map((item) => (
        <View key={item.commitment_key} style={styles.item}>
          <Text style={styles.itemTitle}>{item.title}</Text>
          <Text style={styles.itemDescription}>{item.description}</Text>
          <Text style={styles.tradeoff}>Upside: {item.expected_upside}</Text>
          <Text style={styles.tradeoff}>Downside: {item.expected_downside}</Text>
          <Text style={styles.duration}>Suggested duration: {item.suggested_duration_days} days</Text>

          <TouchableOpacity
            style={[styles.button, busy ? styles.buttonDisabled : null]}
            disabled={busy}
            onPress={() => onActivate(item, { replaceActive: hasActive })}
          >
            <Text style={styles.buttonText}>{hasActive ? 'Replace With This Plan' : 'Commit To This Plan'}</Text>
          </TouchableOpacity>
        </View>
      ))}

      {available.items.length === 0 ? (
        <Text style={styles.empty}>No commitment options available right now.</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: '#dbeafe',
    borderRadius: 12,
    backgroundColor: '#eff6ff',
    padding: 14,
    gap: 8,
  },
  heading: {
    color: '#1e3a8a',
    fontSize: 17,
    fontWeight: '800',
  },
  subheading: {
    color: '#1e40af',
    fontSize: 12,
    lineHeight: 17,
  },
  activeChip: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: 999,
    backgroundColor: '#ffffff',
    paddingVertical: 5,
    paddingHorizontal: 10,
    alignSelf: 'flex-start',
  },
  activeChipText: {
    fontSize: 11,
    fontWeight: '800',
  },
  item: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: 10,
    backgroundColor: '#ffffff',
    padding: 10,
    gap: 4,
  },
  itemTitle: {
    color: '#0f172a',
    fontSize: 14,
    fontWeight: '800',
  },
  itemDescription: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  tradeoff: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  duration: {
    color: '#1e40af',
    fontSize: 11,
    fontWeight: '700',
  },
  button: {
    marginTop: 4,
    borderRadius: 9,
    backgroundColor: '#1d4ed8',
    paddingVertical: 8,
    paddingHorizontal: 10,
    alignItems: 'center',
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  buttonText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '800',
  },
  empty: {
    color: '#64748b',
    fontSize: 12,
  },
});

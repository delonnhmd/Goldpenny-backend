import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import {
  adherenceLabel,
  alignmentLabel,
  driftColor,
  driftSeverityLabel,
  momentumLabel,
  statusBadgeColor,
} from '@/lib/commitmentFormatters';
import { ActiveCommitmentResponse } from '@/types/commitment';

export default function ActiveCommitmentCard({
  commitment,
  busy = false,
  onCancel,
}: {
  commitment: ActiveCommitmentResponse;
  busy?: boolean;
  onCancel?: () => void;
}) {
  const active = commitment.status === 'active' && Boolean(commitment.commitment_key);
  if (!active) {
    return (
      <View style={styles.card}>
        <Text style={styles.heading}>Active Commitment</Text>
        <Text style={styles.empty}>No commitment active. Pick one plan to start follow-through tracking.</Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.heading}>Active Commitment</Text>
        <Text style={[styles.statusBadge, { color: statusBadgeColor(commitment.status) }]}>{commitment.status}</Text>
      </View>

      <Text style={styles.title}>{commitment.title}</Text>
      <Text style={styles.description}>{commitment.description}</Text>

      <View style={styles.metaRow}>
        <Text style={styles.meta}>Days remaining: {commitment.days_remaining}</Text>
        <Text style={styles.meta}>Duration: {commitment.duration_days} days</Text>
      </View>

      <View style={styles.scoreRow}>
        <View style={styles.scoreItem}>
          <Text style={styles.scoreLabel}>Adherence</Text>
          <Text style={styles.scoreValue}>
            {Math.round(commitment.adherence_score)} ({adherenceLabel(commitment.adherence_score)})
          </Text>
        </View>
        <View style={styles.scoreItem}>
          <Text style={styles.scoreLabel}>Momentum</Text>
          <Text style={styles.scoreValue}>
            {Math.round(commitment.momentum_score)} ({momentumLabel(commitment.momentum_score)})
          </Text>
        </View>
      </View>

      <View style={styles.statusRow}>
        <Text style={styles.statusText}>Alignment: {alignmentLabel(commitment.alignment_label)}</Text>
        <Text style={[styles.statusText, { color: driftColor(commitment.drift_level) }]}>
          {driftSeverityLabel(commitment.drift_level)}
        </Text>
      </View>

      <Text style={styles.payoff}>Likely payoff: {commitment.likely_payoff}</Text>
      <Text style={styles.downside}>Risk if abandoned: {commitment.likely_downside}</Text>
      {commitment.suggested_correction ? (
        <Text style={styles.correction}>Course correction: {commitment.suggested_correction}</Text>
      ) : null}

      {onCancel ? (
        <TouchableOpacity
          style={[styles.cancelButton, busy ? styles.buttonDisabled : null]}
          disabled={busy}
          onPress={onCancel}
        >
          <Text style={styles.cancelButtonText}>Cancel Commitment</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 12,
    backgroundColor: '#ffffff',
    padding: 14,
    gap: 8,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  heading: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  statusBadge: {
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  title: {
    color: '#1d4ed8',
    fontSize: 14,
    fontWeight: '900',
  },
  description: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
    flexWrap: 'wrap',
  },
  meta: {
    color: '#475569',
    fontSize: 11,
    fontWeight: '700',
  },
  scoreRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  scoreItem: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 3,
    minWidth: 130,
  },
  scoreLabel: {
    color: '#64748b',
    fontSize: 11,
    fontWeight: '700',
  },
  scoreValue: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: '800',
  },
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
    flexWrap: 'wrap',
  },
  statusText: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '700',
  },
  payoff: {
    color: '#166534',
    fontSize: 12,
    lineHeight: 17,
  },
  downside: {
    color: '#b91c1c',
    fontSize: 12,
    lineHeight: 17,
  },
  correction: {
    color: '#1e40af',
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  cancelButton: {
    marginTop: 2,
    borderRadius: 9,
    backgroundColor: '#334155',
    paddingVertical: 8,
    paddingHorizontal: 10,
    alignItems: 'center',
  },
  cancelButtonText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '800',
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  empty: {
    color: '#64748b',
    fontSize: 12,
    lineHeight: 17,
  },
});

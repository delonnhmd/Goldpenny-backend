import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { feedbackSeverityColor } from '@/lib/commitmentFormatters';
import { CommitmentFeedbackResponse } from '@/types/commitment';

export default function CommitmentFeedbackCard({
  feedback,
}: {
  feedback: CommitmentFeedbackResponse;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Commitment Feedback</Text>
      <Text style={styles.subheading}>Course-correction guidance based on your latest actions.</Text>

      {feedback.items.length > 0 ? (
        feedback.items.slice(0, 4).map((item, index) => (
          <View key={`${item.feedback_type}_${index}`} style={styles.item}>
            <View style={styles.itemHeader}>
              <Text style={styles.itemTitle}>{item.title}</Text>
              <Text style={[styles.severity, { color: feedbackSeverityColor(item.severity) }]}>
                {item.severity}
              </Text>
            </View>
            <Text style={styles.itemBody}>{item.body}</Text>
            {item.suggested_correction ? (
              <Text style={styles.correction}>Fix: {item.suggested_correction}</Text>
            ) : null}
          </View>
        ))
      ) : (
        <Text style={styles.empty}>No commitment feedback yet.</Text>
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
  item: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 4,
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  itemTitle: {
    color: theme.ui.text.onLight,
    fontSize: 13,
    fontWeight: '700',
    flex: 1,
  },
  severity: {
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  itemBody: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  correction: {
    color: theme.ui.action,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  empty: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
  },
});

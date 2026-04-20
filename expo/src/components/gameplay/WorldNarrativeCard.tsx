import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { lockedBadgeText } from '@/lib/worldMemoryFormatters';
import { WorldNarrativeResponse } from '@/types/worldMemory';

export default function WorldNarrativeCard({ narrative }: { narrative: WorldNarrativeResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>World Narrative</Text>
      <Text style={styles.headline}>{narrative.headline}</Text>
      <Text style={styles.body}>{narrative.body}</Text>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>What Is Persisting</Text>
        {narrative.what_is_persisting.slice(0, 3).map((item, index) => (
          <Text key={`persist_${index}`} style={styles.itemText}>- {item}</Text>
        ))}
      </View>

      {narrative.what_is_fading.length > 0 ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>What Is Fading</Text>
          {narrative.what_is_fading.slice(0, 3).map((item, index) => (
            <Text key={`fading_${index}`} style={styles.itemText}>- {item}</Text>
          ))}
        </View>
      ) : null}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>What To Watch Next</Text>
        {narrative.what_to_watch_next.slice(0, 3).map((item, index) => (
          <Text key={`watch_${index}`} style={styles.itemText}>- {item}</Text>
        ))}
      </View>

      <View style={styles.responseBox}>
        <Text style={styles.responseTitle}>Recommended Short Response</Text>
        <Text style={styles.responseText}>{narrative.recommended_short_response}</Text>
      </View>
      <View style={styles.lockedBox}>
        <Text style={styles.lockedBadge}>{lockedBadgeText()}</Text>
        <Text style={styles.lockedText}>{narrative.future_locked_long_response}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.ui.info,
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
  headline: {
    color: theme.ui.action,
    fontSize: 14,
    fontWeight: '800',
  },
  body: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  section: {
    gap: 3,
  },
  sectionTitle: {
    color: theme.ui.text.onLight,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  itemText: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 16,
  },
  responseBox: {
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 4,
  },
  responseTitle: {
    color: theme.ui.action,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  responseText: {
    color: theme.ui.action,
    fontSize: 12,
    lineHeight: 17,
  },
  lockedBox: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 4,
  },
  lockedBadge: {
    color: theme.ui.text.onLightMuted,
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  lockedText: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
});

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

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
    borderColor: '#dbeafe',
    borderRadius: 12,
    backgroundColor: '#f8fbff',
    padding: 14,
    gap: 8,
  },
  heading: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  headline: {
    color: '#1e3a8a',
    fontSize: 14,
    fontWeight: '800',
  },
  body: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  section: {
    gap: 3,
  },
  sectionTitle: {
    color: '#0f172a',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  itemText: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 16,
  },
  responseBox: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: 10,
    backgroundColor: '#eff6ff',
    padding: 10,
    gap: 4,
  },
  responseTitle: {
    color: '#1e3a8a',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  responseText: {
    color: '#1e40af',
    fontSize: 12,
    lineHeight: 17,
  },
  lockedBox: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#ffffff',
    padding: 10,
    gap: 4,
  },
  lockedBadge: {
    color: '#475569',
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  lockedText: {
    color: '#64748b',
    fontSize: 12,
    lineHeight: 17,
  },
});

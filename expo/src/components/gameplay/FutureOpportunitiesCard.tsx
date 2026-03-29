import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { lockedBadgeText } from '@/lib/economyPresentationFormatters';
import { FutureOpportunityTeasersResponse } from '@/types/economyPresentation';

export default function FutureOpportunitiesCard({ teasers }: { teasers: FutureOpportunityTeasersResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Future Opportunities</Text>
      <Text style={styles.subheading}>Planned systems, not currently playable.</Text>
      {teasers.teasers.map((item) => (
        <View key={item.teaser_key} style={styles.item}>
          <View style={styles.itemHeader}>
            <Text style={styles.title}>{item.title}</Text>
            <Text style={styles.badge}>{lockedBadgeText()}</Text>
          </View>
          <Text style={styles.body}>{item.body}</Text>
        </View>
      ))}
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
    fontSize: 16,
    fontWeight: '800',
  },
  subheading: {
    color: '#64748b',
    fontSize: 12,
    fontWeight: '600',
  },
  item: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 4,
  },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 6,
    flexWrap: 'wrap',
  },
  title: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: '700',
  },
  badge: {
    color: '#b45309',
    fontSize: 11,
    fontWeight: '900',
  },
  body: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 17,
  },
});

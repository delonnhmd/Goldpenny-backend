import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

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
    borderColor: theme.ui.border,
    borderRadius: 12,
    backgroundColor: theme.ui.bg.sheet,
    padding: 14,
    gap: 8,
  },
  heading: {
    color: theme.ui.text.onLight,
    fontSize: 16,
    fontWeight: '800',
  },
  subheading: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    fontWeight: '600',
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
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 6,
    flexWrap: 'wrap',
  },
  title: {
    color: theme.ui.text.onLight,
    fontSize: 13,
    fontWeight: '700',
  },
  badge: {
    color: theme.ui.warning,
    fontSize: 11,
    fontWeight: '900',
  },
  body: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
});

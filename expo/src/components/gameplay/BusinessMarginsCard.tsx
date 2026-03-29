import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { costPressureTone, marginTone } from '@/lib/economyPresentationFormatters';
import { BusinessMarginsResponse } from '@/types/economyPresentation';

function businessLabel(key: string): string {
  if (key === 'fruit_shop') return 'Fruit Shop';
  if (key === 'food_truck') return 'Food Truck';
  return key.replace(/_/g, ' ').replace(/\b\w/g, (v) => v.toUpperCase());
}

export default function BusinessMarginsCard({ margins }: { margins: BusinessMarginsResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Business Margins</Text>
      {margins.items.map((item) => (
        <View key={item.business_key} style={styles.item}>
          <View style={styles.titleRow}>
            <Text style={styles.title}>{businessLabel(item.business_key)}</Text>
            <Text style={[styles.margin, { color: marginTone(item.margin_outlook) }]}>
              {String(item.margin_outlook).toUpperCase()}
            </Text>
          </View>
          <Text style={styles.meta}>
            Demand: {item.demand_outlook} • Cost pressure:{' '}
            <Text style={{ color: costPressureTone(item.cost_pressure), fontWeight: '800' }}>
              {item.cost_pressure}
            </Text>
          </Text>
          <Text style={styles.summary}>{item.short_explainer}</Text>
          {item.risk_factors.length > 0 ? (
            <Text style={styles.riskText}>Risks: {item.risk_factors.slice(0, 2).join(' | ')}</Text>
          ) : null}
          {item.opportunity_factors.length > 0 ? (
            <Text style={styles.oppText}>Opportunities: {item.opportunity_factors.slice(0, 2).join(' | ')}</Text>
          ) : null}
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
    fontSize: 17,
    fontWeight: '800',
  },
  item: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 4,
  },
  titleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  title: {
    color: '#0f172a',
    fontSize: 14,
    fontWeight: '800',
  },
  margin: {
    fontSize: 11,
    fontWeight: '900',
  },
  meta: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '600',
  },
  summary: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 17,
  },
  riskText: {
    color: '#b91c1c',
    fontSize: 12,
    lineHeight: 17,
  },
  oppText: {
    color: '#166534',
    fontSize: 12,
    lineHeight: 17,
  },
});

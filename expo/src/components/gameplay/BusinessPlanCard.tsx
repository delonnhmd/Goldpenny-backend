import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { BusinessPlanResponse } from '@/types/strategicPlanning';

function businessTitle(key: string): string {
  if (key === 'fruit_shop') return 'Fruit Shop';
  if (key === 'food_truck') return 'Food Truck';
  return key.replace(/_/g, ' ');
}

export default function BusinessPlanCard({ plan }: { plan: BusinessPlanResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Business Plan (3-7 Days)</Text>
      <Text style={styles.copy}>Short-horizon positioning for each business under current market conditions.</Text>

      {plan.items.map((item) => (
        <View key={item.business_key} style={styles.item}>
          <View style={styles.itemHeader}>
            <Text style={styles.itemTitle}>{businessTitle(item.business_key)}</Text>
            <Text style={styles.mode}>
              {item.business_present ? `Mode: ${item.current_mode || 'default'}` : 'Not active'}
            </Text>
          </View>
          <Text style={styles.line}>Demand outlook: {item.demand_outlook}</Text>
          <Text style={styles.line}>Input-cost outlook: {item.input_cost_outlook}</Text>
          <Text style={styles.line}>Margin stability: {item.margin_stability}</Text>
          <Text style={styles.recommendation}>{item.recommendation_over_horizon}</Text>
          <Text style={styles.watch}>Watch item: {item.key_watch_item}</Text>
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
    gap: 10,
  },
  heading: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  copy: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 17,
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
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  itemTitle: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: '800',
  },
  mode: {
    color: '#334155',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  line: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  recommendation: {
    color: '#0f172a',
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  watch: {
    color: '#1e3a8a',
    fontSize: 12,
    lineHeight: 17,
  },
});

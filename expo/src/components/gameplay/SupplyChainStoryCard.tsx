import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { SupplyChainStoryResponse, SupplyChainSummaryResponse } from '@/types/supplyChain';

export default function SupplyChainStoryCard({
  summary,
  story,
  warnings,
  opportunities,
}: {
  summary: SupplyChainSummaryResponse;
  story: SupplyChainStoryResponse;
  warnings?: string[];
  opportunities?: string[];
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Supply Chain Pulse</Text>
      <Text style={styles.summary}>{summary.short_summary}</Text>
      <Text style={styles.story}>{story.shortage_story}</Text>

      <View style={styles.metaGrid}>
        <View style={styles.metaBox}>
          <Text style={styles.metaLabel}>Top Bottleneck</Text>
          <Text style={styles.metaValue}>{summary.top_bottleneck_node || 'None'}</Text>
        </View>
        <View style={styles.metaBox}>
          <Text style={styles.metaLabel}>Most Affected Basket</Text>
          <Text style={styles.metaValue}>{summary.most_affected_basket || 'None'}</Text>
        </View>
        <View style={styles.metaBox}>
          <Text style={styles.metaLabel}>Best Job Opportunity</Text>
          <Text style={styles.metaValue}>{summary.best_job_opportunity || 'None'}</Text>
        </View>
      </View>

      <View style={styles.columns}>
        <View style={styles.column}>
          <Text style={styles.columnTitle}>Bottleneck Highlights</Text>
          {story.bottleneck_highlights.slice(0, 3).map((item, index) => (
            <Text key={`bn_${index}`} style={styles.itemText}>• {item}</Text>
          ))}
        </View>
        <View style={styles.column}>
          <Text style={styles.columnTitle}>Job Opportunity Hints</Text>
          {story.job_opportunity_hints.slice(0, 3).map((item, index) => (
            <Text key={`job_${index}`} style={styles.itemText}>• {item}</Text>
          ))}
        </View>
        <View style={styles.column}>
          <Text style={styles.columnTitle}>Current Actions</Text>
          {story.practical_current_actions.slice(0, 3).map((item, index) => (
            <Text key={`action_${index}`} style={styles.itemText}>• {item}</Text>
          ))}
        </View>
      </View>

      {warnings && warnings.length > 0 ? (
        <View style={styles.signalBox}>
          <Text style={[styles.signalTitle, styles.warningTitle]}>Backend Warnings</Text>
          {warnings.slice(0, 3).map((item, index) => (
            <Text key={`warning_${index}`} style={styles.itemText}>• {item}</Text>
          ))}
        </View>
      ) : null}

      {opportunities && opportunities.length > 0 ? (
        <View style={styles.signalBox}>
          <Text style={[styles.signalTitle, styles.opportunityTitle]}>Backend Opportunities</Text>
          {opportunities.slice(0, 3).map((item, index) => (
            <Text key={`opp_${index}`} style={styles.itemText}>• {item}</Text>
          ))}
        </View>
      ) : null}
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
  summary: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: '700',
  },
  story: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 18,
  },
  metaGrid: {
    gap: 8,
  },
  metaBox: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 2,
  },
  metaLabel: {
    color: '#475569',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  metaValue: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: '700',
  },
  columns: {
    gap: 8,
  },
  column: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 4,
  },
  columnTitle: {
    color: '#0f172a',
    fontSize: 12,
    fontWeight: '700',
  },
  itemText: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 17,
  },
  signalBox: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 4,
  },
  signalTitle: {
    fontSize: 12,
    fontWeight: '800',
  },
  warningTitle: {
    color: '#b91c1c',
  },
  opportunityTitle: {
    color: '#166534',
  },
});

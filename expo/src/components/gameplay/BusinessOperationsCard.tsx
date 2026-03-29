// Gold Penny — BusinessOperationsCard
// Primary-section interactive card for Fruit Shop / Food Truck daily operation.
// Shows real-time economy signals (margins, cost pressure, demand) from the backend
// world-state alongside the player's inventory and today's operate action.
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import { theme } from '@/design/theme';
import { costPressureTone, marginTone } from '@/lib/economyPresentationFormatters';
import { BusinessMarginItem } from '@/types/economyPresentation';
import { BusinessPlanItem } from '@/types/strategicPlanning';
import { BusinessProfitSnapshot, PlayerBusinessRecord } from '@/types/business';

function businessLabel(type: string): string {
  if (type === 'fruit_shop') return 'Fruit Shop';
  if (type === 'food_truck') return 'Food Truck';
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function operationReadiness(outlook: string | null | undefined): string {
  if (outlook === 'favorable') return 'Worth running today';
  if (outlook === 'mixed') return 'Playable, but margins are thin';
  if (outlook === 'pressured') return 'High-risk operating day';
  return 'Check the latest demand and cost signals';
}

interface BusinessOperationsCardProps {
  activeRecord: PlayerBusinessRecord;
  profitSnapshot: BusinessProfitSnapshot | null;
  margins: BusinessMarginItem | null;
  plan: BusinessPlanItem | null;
  operatedToday: boolean;
  sessionActive: boolean;
  isExecuting: boolean;
  onOperate: () => void;
}

export default function BusinessOperationsCard({
  activeRecord,
  profitSnapshot,
  margins,
  plan,
  operatedToday,
  sessionActive,
  isExecuting,
  onOperate,
}: BusinessOperationsCardProps) {
  const operateDisabled = operatedToday || !sessionActive || isExecuting;
  const operateLabel = operatedToday ? 'Operated Today \u2713' : 'Run Business Today';
  const latestProfit = profitSnapshot?.latest_daily_profit_xgp;
  const trailingProfit = profitSnapshot?.trailing_7d_profit_xgp;
  const inventoryUnits = activeRecord.inventory_produce_units + activeRecord.inventory_essentials_units + activeRecord.inventory_protein_units;
  const readinessCopy = operationReadiness(margins?.margin_outlook);
  const whyItMatters = margins?.short_explainer || 'Running the business turns stocked inventory into same-day cash, but weak margins can erase the upside.';
  const recommendation = plan?.recommendation_over_horizon || (margins?.margin_outlook === 'pressured'
    ? 'Recommended action: protect cash and inventory unless you urgently need operating income.'
    : 'Recommended action: operate only if the expected cash gain is worth today\'s time and cost pressure.');
  const watchItem = plan?.key_watch_item || (inventoryUnits <= 2
    ? 'Inventory is low, so one weak run can leave you with little room to recover.'
    : 'Watch demand and input costs before committing more inventory.');
  const inventoryStatus = inventoryUnits <= 0
    ? 'No inventory loaded. Restock before trying to rely on this business for cash.'
    : inventoryUnits <= 2
      ? 'Inventory is running low, so today\'s operating window is fragile.'
      : null;

  return (
    <View style={styles.card}>
      <View style={styles.titleRow}>
        <View style={styles.titleBlock}>
          <Text style={styles.kicker}>Business today</Text>
          <Text style={styles.title}>{businessLabel(activeRecord.business_type)}</Text>
        </View>
        <View style={styles.modeBadge}>
          <Text style={styles.modeBadgeText}>{activeRecord.operating_mode ? activeRecord.operating_mode.replace(/_/g, ' ') : 'standard mode'}</Text>
        </View>
      </View>

      {margins ? (
        <View style={styles.signalsRow}>
          <View style={[styles.signalChip, { backgroundColor: `${marginTone(margins.margin_outlook)}12` }]}>
            <Text style={[styles.signalChipText, { color: marginTone(margins.margin_outlook) }]}>
              {String(margins.margin_outlook).replace(/_/g, ' ')}
            </Text>
          </View>
          <View style={styles.signalChip}>
            <Text style={styles.signalChipText}>Demand {margins.demand_outlook}</Text>
          </View>
          <View style={[styles.signalChip, { backgroundColor: `${costPressureTone(margins.cost_pressure)}12` }]}>
            <Text style={[styles.signalChipText, { color: costPressureTone(margins.cost_pressure) }]}>Cost {margins.cost_pressure}</Text>
          </View>
        </View>
      ) : null}

      <View style={styles.outcomeBox}>
        <Text style={styles.outcomeLabel}>Should you run it?</Text>
        <Text style={styles.outcomeTitle}>{readinessCopy}</Text>
        <Text style={styles.explainer} numberOfLines={3}>{whyItMatters}</Text>
      </View>

      <View style={styles.metricRow}>
        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>Last result</Text>
          <Text style={[styles.metricValue, latestProfit != null ? { color: latestProfit >= 0 ? '#166534' : '#b91c1c' } : null]}>
            {latestProfit != null ? `${latestProfit >= 0 ? '+' : ''}${latestProfit.toFixed(1)} XGP` : 'No run yet'}
          </Text>
        </View>
        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>7d trend</Text>
          <Text style={[styles.metricValue, trailingProfit != null ? { color: trailingProfit >= 0 ? '#166534' : '#b91c1c' } : null]}>
            {trailingProfit != null ? `${trailingProfit >= 0 ? '+' : ''}${trailingProfit.toFixed(1)} XGP` : 'No trend yet'}
          </Text>
        </View>
        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>Inventory</Text>
          <Text style={styles.metricValue}>{inventoryUnits} units</Text>
        </View>
      </View>

      <View style={styles.whyBox}>
        <Text style={styles.whyTitle}>Why this matters</Text>
        <Text style={styles.recommendation} numberOfLines={3}>{recommendation}</Text>
        <Text style={styles.watchText} numberOfLines={2}>Watch: {watchItem}</Text>
      </View>

      {margins && (margins.risk_factors.length > 0 || margins.opportunity_factors.length > 0) ? (
        <View style={styles.bullets}>
          {margins.risk_factors[0] ? (
            <View style={styles.calloutBox}>
              <Text style={styles.calloutLabel}>Risk</Text>
              <Text style={styles.riskText} numberOfLines={2}>{margins.risk_factors[0]}</Text>
            </View>
          ) : null}
          {margins.opportunity_factors[0] ? (
            <View style={styles.calloutBox}>
              <Text style={styles.calloutLabel}>Upside</Text>
              <Text style={styles.oppText} numberOfLines={2}>{margins.opportunity_factors[0]}</Text>
            </View>
          ) : null}
        </View>
      ) : null}

      {inventoryStatus ? <Text style={styles.inventoryWarning}>{inventoryStatus}</Text> : null}

      {activeRecord.inventory_produce_units > 0
        || activeRecord.inventory_essentials_units > 0
        || activeRecord.inventory_protein_units > 0 ? (
        <View style={styles.inventoryRow}>
          {activeRecord.inventory_produce_units > 0 ? (
            <Text style={styles.inventoryItem}>Produce: {activeRecord.inventory_produce_units}u</Text>
          ) : null}
          {activeRecord.inventory_essentials_units > 0 ? (
            <Text style={styles.inventoryItem}>Essentials: {activeRecord.inventory_essentials_units}u</Text>
          ) : null}
          {activeRecord.inventory_protein_units > 0 ? (
            <Text style={styles.inventoryItem}>Protein: {activeRecord.inventory_protein_units}u</Text>
          ) : null}
        </View>
      ) : null}

      {!sessionActive ? (
        <Text style={styles.blockerText}>Day ended — start the next day to operate.</Text>
      ) : null}

      <PrimaryButton
        label={isExecuting && !operatedToday ? 'Running...' : operateLabel}
        onPress={operateDisabled ? undefined : onOperate}
        disabled={operateDisabled}
        loading={isExecuting && !operatedToday}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: '#dbe4ef',
    borderRadius: theme.radius.xl,
    backgroundColor: '#ffffff',
    padding: theme.spacing.lg,
    gap: theme.spacing.md,
  },
  titleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: theme.spacing.sm,
  },
  titleBlock: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  kicker: {
    color: theme.color.info,
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.7,
    fontWeight: '800',
  },
  title: {
    color: theme.color.textPrimary,
    ...theme.typography.headingMd,
    fontWeight: '800',
  },
  modeBadge: {
    borderRadius: theme.radius.pill,
    backgroundColor: '#f8fafc',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  modeBadgeText: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    fontWeight: '700',
    textTransform: 'capitalize',
  },
  signalsRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  signalChip: {
    borderRadius: theme.radius.pill,
    backgroundColor: '#f8fafc',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  signalChipText: {
    color: theme.color.textPrimary,
    ...theme.typography.caption,
    fontWeight: '800',
  },
  outcomeBox: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: theme.radius.xl,
    backgroundColor: '#f8fbff',
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  outcomeLabel: {
    color: '#1d4ed8',
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '800',
  },
  outcomeTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
    fontWeight: '800',
  },
  recommendation: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
    fontWeight: '600',
  },
  explainer: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  metricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  metricCard: {
    flex: 1,
    minWidth: 108,
    borderWidth: 1,
    borderColor: '#dbe4ef',
    borderRadius: theme.radius.lg,
    backgroundColor: '#ffffff',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  metricLabel: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  metricValue: {
    color: theme.color.textPrimary,
    ...theme.typography.bodyMd,
    fontWeight: '800',
  },
  whyBox: {
    gap: theme.spacing.xs,
  },
  whyTitle: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '800',
  },
  watchText: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  bullets: {
    gap: theme.spacing.sm,
  },
  calloutBox: {
    borderRadius: theme.radius.lg,
    backgroundColor: '#f8fafc',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  calloutLabel: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  riskText: {
    color: '#b91c1c',
    ...theme.typography.bodySm,
  },
  oppText: {
    color: '#166534',
    ...theme.typography.bodySm,
  },
  inventoryRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
  },
  inventoryItem: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    fontWeight: '700',
    borderRadius: theme.radius.pill,
    backgroundColor: '#f8fafc',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  inventoryWarning: {
    color: '#b45309',
    ...theme.typography.bodySm,
    fontWeight: '600',
  },
  blockerText: {
    color: '#b45309',
    ...theme.typography.bodySm,
    fontWeight: '600',
  },
});

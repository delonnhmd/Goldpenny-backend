import { useFocusEffect } from '@react-navigation/native';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { alpha, theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import {
  buildSlotAddress,
  businessLabel,
  createEmptyBusinessSandboxState,
  deriveActiveBusinessProfile,
} from '@/lib/businessSandbox';
import {
  buyBusinessInventory,
  getSupplierItems,
  SupplierInventoryPurchaseLineInput,
} from '@/lib/api/business';
import { readBusinessSandboxState } from '@/lib/businessSandboxPersistence';
import { formatMoney } from '@/lib/gameplayFormatters';
import type {
  BusinessDailyOperationRecord,
  BusinessInventoryItem,
  BusinessSandboxState,
  PlayerBusinessRecord,
  SupplierItemRecord,
} from '@/types/business';
import type { GameplayActionKey } from '@/types/gameplay';

import { useGameplayLoop } from '../context';
import {
  GameplayCompactMetricRows,
  GameplayStatCard,
  GameplaySummaryCard,
  GameplayWarningBanner,
  toneFromSignedValue,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

function canonicalActionKey(actionKey: string): GameplayActionKey | string {
  const raw = String(actionKey || '').toLowerCase().trim();
  if (!raw) return '';
  if (raw === 'operate_business' || (raw.includes('operate') && raw.includes('business'))) return 'operate_business';
  return raw;
}

function normalizeError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  if (!raw) return 'Something went wrong. Please try again.';
  const colonIndex = raw.indexOf(':');
  return colonIndex > -1 ? raw.slice(colonIndex + 1).trim() : raw;
}

function inventoryUnitsForBusiness(business: PlayerBusinessRecord | null): number {
  if (!business) return 0;
  if (typeof business.inventory_total_units === 'number') {
    return Number(business.inventory_total_units || 0);
  }
  return Number(business.inventory_produce_units ?? 0)
    + Number(business.inventory_essentials_units ?? 0)
    + Number(business.inventory_protein_units ?? 0);
}

function inventoryValueForBusiness(business: PlayerBusinessRecord | null): number {
  if (!business) return 0;
  if (typeof business.inventory_estimated_value_xgp === 'number') {
    return Number(business.inventory_estimated_value_xgp || 0);
  }
  return (business.inventory_items || []).reduce(
    (sum, item) => sum + Number(item.estimated_value_xgp || (item.quantity * item.avg_unit_cost) || 0),
    0,
  );
}

function latestBusinessLog(business: PlayerBusinessRecord | null): BusinessDailyOperationRecord | null {
  return business?.latest_daily_log || null;
}

function linkedLotForBusiness(state: BusinessSandboxState, businessId: string | null | undefined) {
  if (!businessId) return null;
  return state.owned_lots.find(
    (lot) => lot.linked_business_id === businessId || lot.placed_business_id === businessId,
  ) || null;
}

function supplierQuantityValue(input: string): number {
  const normalized = String(input || '').replace(/[^\d]/g, '');
  const value = Number(normalized || 0);
  return Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
}

function formatDaysLeft(daysLeft?: number | null): string {
  if (daysLeft == null || !Number.isFinite(daysLeft)) return 'Unknown';
  if (daysLeft <= 0) return '0 days';
  if (daysLeft < 1) return '<1 day';
  return `${daysLeft.toFixed(daysLeft < 10 ? 1 : 0)} day${daysLeft >= 1.95 ? 's' : ''}`;
}

function SummaryStatRow({
  business,
  linkedAddress,
  latestLog,
  inventoryValueXgp,
}: {
  business: PlayerBusinessRecord;
  linkedAddress: string | null;
  latestLog: BusinessDailyOperationRecord | null;
  inventoryValueXgp: number;
}) {
  return (
    <>
      <View style={styles.metricRow}>
        <GameplayStatCard
          label="Business Type"
          value={businessLabel(business.business_type)}
          tone="neutral"
          note={business.business_name || 'Starter business'}
        />
        <GameplayStatCard
          label="Reputation"
          value={`${Math.round(Number(business.reputation || 0))}/100`}
          tone={Number(business.reputation || 0) >= 70 ? 'positive' : Number(business.reputation || 0) >= 50 ? 'warning' : 'neutral'}
          note="Local customer trust"
        />
        <GameplayStatCard
          label="Cash Invested"
          value={formatMoney(Number(business.cash_invested_xgp || 0))}
          tone="neutral"
          note={`Inventory value ${formatMoney(inventoryValueXgp)}`}
        />
        <GameplayStatCard
          label="Last Operated"
          value={business.last_operated_day ? `Day ${business.last_operated_day}` : 'Not run yet'}
          tone={business.last_operated_day ? 'info' : 'warning'}
          note={latestLog?.as_of_date || 'Run once inventory is ready'}
        />
      </View>

      <GameplayCompactMetricRows
        items={[
          { label: 'Region', value: business.region_key || 'No region linked yet' },
          { label: 'Linked slot', value: linkedAddress || 'Place the business on a purchased lot from the map' },
          { label: 'Inventory units', value: String(inventoryUnitsForBusiness(business)) },
          { label: 'Estimated stock left', value: formatDaysLeft(business.estimated_days_of_stock_left) },
          { label: 'Business value', value: formatMoney(Number(business.business_estimated_value_xgp || 0)) },
        ]}
      />
    </>
  );
}

function InventoryGrid({
  items,
}: {
  items: BusinessInventoryItem[];
}) {
  if (!items.length) {
    return (
      <GameplayWarningBanner
        title="No supplier inventory on hand"
        message="Buy stock from the supplier market below before operating again."
        tone="warning"
      />
    );
  }

  return (
    <View style={styles.inventoryGrid}>
      {items.map((item) => (
        <View key={item.item_id} style={styles.inventoryCard}>
          <View style={styles.inventoryCardHeader}>
            <Text style={styles.inventoryTitle}>{item.display_name}</Text>
            <Text style={styles.inventoryQuantity}>{item.quantity} {item.unit_label}</Text>
          </View>
          <Text style={styles.inventoryMeta}>
            Avg cost {formatMoney(Number(item.avg_unit_cost || 0), 2)} | Retail {formatMoney(Number(item.retail_price || 0), 2)}
          </Text>
          <Text style={styles.inventoryMeta}>
            Value {formatMoney(Number(item.estimated_value_xgp || (item.quantity * item.avg_unit_cost) || 0))} | Days left {formatDaysLeft(item.estimated_days_of_stock_left)}
          </Text>
          <Text style={styles.inventoryMeta}>
            Spoilage {(Number(item.spoilage_rate || 0) * 100).toFixed(0)}% | Demand {Number(item.demand_weight || 0).toFixed(2)}
          </Text>
        </View>
      ))}
    </View>
  );
}

function DailyLogBreakdown({
  latestLog,
}: {
  latestLog: BusinessDailyOperationRecord | null;
}) {
  if (!latestLog) {
    return (
      <Text style={styles.supportingCopy}>
        No completed business day yet. Buy inventory, then run the business once to unlock daily revenue, labor, COGS, spoilage, and stock-left tracking.
      </Text>
    );
  }

  const unitsSoldSummary = Object.entries(latestLog.units_sold_by_item || {})
    .filter(([, quantity]) => Number(quantity || 0) > 0)
    .map(([itemId, quantity]) => `${itemId.replace(/_/g, ' ')} ${Number(quantity).toFixed(Number(quantity) % 1 === 0 ? 0 : 1)}`)
    .join(' | ');

  return (
    <View style={styles.breakdownStack}>
      <GameplayCompactMetricRows
        items={[
          { label: 'Revenue', value: formatMoney(Number(latestLog.gross_revenue_xgp || latestLog.revenue_xgp || 0)), tone: 'positive' },
          { label: 'Stock cost / COGS', value: formatMoney(Number(latestLog.cost_of_goods_sold_xgp || latestLog.cogs_xgp || 0)), tone: 'warning' },
          { label: 'Labor', value: formatMoney(Number(latestLog.labor_cost_xgp || 0)), tone: 'warning' },
          { label: 'Overhead', value: formatMoney(Number(latestLog.overhead_xgp || 0)), tone: 'warning' },
          { label: 'Fuel', value: formatMoney(Number(latestLog.fuel_cost_xgp || 0)), tone: Number(latestLog.fuel_cost_xgp || 0) > 0 ? 'warning' : 'neutral' },
          { label: 'Maintenance', value: formatMoney(Number(latestLog.maintenance_cost_xgp || 0)), tone: Number(latestLog.maintenance_cost_xgp || 0) > 0 ? 'warning' : 'neutral' },
          { label: 'Spoilage', value: formatMoney(Number(latestLog.spoilage_loss_xgp || 0)), tone: Number(latestLog.spoilage_loss_xgp || 0) > 0 ? 'danger' : 'neutral' },
          { label: 'Net profit', value: formatMoney(Number(latestLog.net_profit_xgp || 0)), tone: toneFromSignedValue(Number(latestLog.net_profit_xgp || 0)) },
          { label: 'Remaining inventory', value: formatMoney(Number(latestLog.remaining_inventory_value_xgp || 0)) },
          { label: 'Stock left', value: formatDaysLeft(latestLog.estimated_days_of_stock_left) },
        ]}
      />

      {unitsSoldSummary ? (
        <Text style={styles.supportingCopy}>Units sold: {unitsSoldSummary}</Text>
      ) : null}

      {Number(latestLog.lost_sales_units || 0) > 0 ? (
        <Text style={styles.warningText}>
          Lost sales: {Number(latestLog.lost_sales_units || 0).toFixed(0)} potential units due to low inventory.
        </Text>
      ) : null}
    </View>
  );
}

export default function BusinessScreen() {
  useScreenTimer('business');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const [sandboxBusinessState, setSandboxBusinessState] = useState<BusinessSandboxState>(
    createEmptyBusinessSandboxState(loop.playerId),
  );
  const [supplierItems, setSupplierItems] = useState<SupplierItemRecord[]>([]);
  const [supplierLoading, setSupplierLoading] = useState(false);
  const [supplierError, setSupplierError] = useState<string | null>(null);
  const [purchaseBusy, setPurchaseBusy] = useState(false);
  const [quantityByItem, setQuantityByItem] = useState<Record<string, string>>({});

  useFocusEffect(useCallback(() => {
    let active = true;
    void readBusinessSandboxState(loop.playerId).then((state) => {
      if (active) setSandboxBusinessState(state);
    });
    return () => {
      active = false;
    };
  }, [loop.playerId]));

  const activeBusiness = useMemo(
    () => {
      const businesses = loop.businesses?.businesses || [];
      return businesses.find((item) => item.is_active) || null;
    },
    [loop.businesses?.businesses],
  );

  useEffect(() => {
    let active = true;
    if (!activeBusiness) {
      setSupplierItems([]);
      setSupplierError(null);
      setQuantityByItem({});
      return () => {
        active = false;
      };
    }

    setSupplierLoading(true);
    setSupplierError(null);
    void getSupplierItems(String(activeBusiness.business_type))
      .then((response) => {
        if (!active) return;
        setSupplierItems(response.items || []);
        setQuantityByItem((current) => {
          const next: Record<string, string> = {};
          for (const item of response.items || []) {
            if (current[item.item_id]) next[item.item_id] = current[item.item_id];
          }
          return next;
        });
      })
      .catch((error) => {
        if (!active) return;
        setSupplierError(normalizeError(error));
        setSupplierItems([]);
      })
      .finally(() => {
        if (active) setSupplierLoading(false);
      });

    return () => {
      active = false;
    };
  }, [activeBusiness?.business_id, activeBusiness?.business_type]);

  const starterOptions = useMemo(
    () => loop.businesses?.starter_options || [
      { business_type: 'fruit_shop', label: 'Fruit Shop', cost_xgp: 500 },
      { business_type: 'food_truck', label: 'Food Truck', cost_xgp: 1200 },
    ],
    [loop.businesses?.starter_options],
  );

  const operatedToday = loop.dailySession.actionsTakenToday.some(
    (entry) => canonicalActionKey(entry.action_key) === 'operate_business' && entry.success,
  );

  const linkedLot = useMemo(
    () => linkedLotForBusiness(sandboxBusinessState, activeBusiness?.business_id),
    [activeBusiness?.business_id, sandboxBusinessState],
  );

  const activeBusinessProfile = useMemo(
    () => deriveActiveBusinessProfile({
      activeBusiness,
      sandboxState: sandboxBusinessState,
      latestProfitXgp: Number(loop.businesses?.profit_snapshot.latest_daily_profit_xgp || 0),
      trailingProfitXgp: Number(loop.businesses?.profit_snapshot.trailing_7d_profit_xgp || 0),
      dayNumber: Number(loop.authoritativeState?.day_number ?? 1),
    }),
    [
      activeBusiness,
      loop.authoritativeState?.day_number,
      loop.businesses?.profit_snapshot.latest_daily_profit_xgp,
      loop.businesses?.profit_snapshot.trailing_7d_profit_xgp,
      sandboxBusinessState,
    ],
  );

  const linkedAddress = useMemo(() => {
    if (linkedLot?.address) return linkedLot.address;
    if (!linkedLot?.tile_key) return null;
    return buildSlotAddress(linkedLot.district_key, linkedLot.district_label || linkedLot.tile_key, linkedLot.y, linkedLot.x);
  }, [linkedLot]);

  const inventoryItems = useMemo(
    () => activeBusiness?.inventory_items || [],
    [activeBusiness?.inventory_items],
  );

  const latestLog = useMemo(
    () => latestBusinessLog(activeBusiness),
    [activeBusiness],
  );

  const inventoryUnits = inventoryUnitsForBusiness(activeBusiness);
  const inventoryValueXgp = inventoryValueForBusiness(activeBusiness);
  const restockWarning = activeBusiness?.restock_warning || latestLog?.restock_warning || null;
  const noInventory = inventoryUnits <= 0;
  const cashOnHand = Number(loop.authoritativeState?.player_state.cash ?? loop.dashboard?.stats.cash_xgp ?? 0);

  const purchaseLines = useMemo(
    () => supplierItems
      .map((item) => ({
        item_id: item.item_id,
        quantity: supplierQuantityValue(quantityByItem[item.item_id] || ''),
        unitCost: Number(item.current_wholesale_cost || 0),
      }))
      .filter((item) => item.quantity > 0),
    [quantityByItem, supplierItems],
  );

  const purchaseTotalXgp = useMemo(
    () => purchaseLines.reduce((sum, line) => sum + (line.quantity * line.unitCost), 0),
    [purchaseLines],
  );

  const handleQuantityChange = useCallback((itemId: string, rawValue: string) => {
    const sanitized = String(rawValue || '').replace(/[^\d]/g, '');
    setQuantityByItem((current) => ({
      ...current,
      [itemId]: sanitized,
    }));
  }, []);

  const handleBuyInventory = useCallback(async () => {
    if (!activeBusiness) return;
    if (!purchaseLines.length) {
      loop.setFeedback({
        tone: 'info',
        message: 'Enter a supplier quantity before buying inventory.',
      });
      return;
    }

    setPurchaseBusy(true);
    try {
      const payload: SupplierInventoryPurchaseLineInput[] = purchaseLines.map((line) => ({
        item_id: line.item_id,
        quantity: line.quantity,
      }));
      const result = await buyBusinessInventory(loop.playerId, activeBusiness.business_id, payload);
      setQuantityByItem({});
      await loop.refresh({ silent: true });
      loop.setFeedback({
        tone: 'success',
        message: `Bought inventory for ${formatMoney(result.total_purchase_cost_xgp)}. Cash left ${formatMoney(result.cash_after_xgp)}.`,
      });
    } catch (error) {
      loop.setFeedback({
        tone: 'error',
        message: normalizeError(error),
      });
    } finally {
      setPurchaseBusy(false);
    }
  }, [activeBusiness, loop, purchaseLines]);

  const runDisabled = Boolean(
    !activeBusiness
    || loop.executingAction
    || operatedToday
    || loop.dailySession.sessionStatus !== 'active'
    || noInventory,
  );

  return (
    <GameplayLoopScaffold
      title="Business"
      subtitle="Supplier inventory, daily profit, and real operating costs"
      activeNavKey="business"
    >
      {!activeBusiness ? (
        <GameplaySummaryCard
          eyebrow="Start Business"
          title="Open a business, then stock it before running"
          subtitle="The backend now treats inventory as real operating stock. Buy land, open a business, purchase supplier inventory, and then operate once per day."
        >
          <View style={styles.starterList}>
            {starterOptions.map((option) => {
              const need = Math.max(Number(option.cost_xgp || 0) - cashOnHand, 0);
              return (
                <View key={String(option.business_type)} style={styles.starterCard}>
                  <Text style={styles.starterTitle}>{option.label}</Text>
                  <Text style={styles.starterLine}>Startup cost {formatMoney(Number(option.cost_xgp || 0))}</Text>
                  <Text style={styles.starterLine}>Cash on hand {formatMoney(cashOnHand)}</Text>
                  <Text style={[styles.starterLine, need > 0 ? styles.needText : styles.readyText]}>
                    {need > 0 ? `Need ${formatMoney(need)} more` : 'Ready to open'}
                  </Text>
                </View>
              );
            })}
          </View>
          <PrimaryButton
            label="Open Map And Choose A Site"
            onPress={() => onboarding.navigateTo('map')}
            style={styles.fullWidthButton}
          />
        </GameplaySummaryCard>
      ) : (
        <>
          {restockWarning ? (
            <GameplayWarningBanner
              title="Restock reminder"
              message={restockWarning}
              tone={noInventory ? 'danger' : 'warning'}
            />
          ) : null}

          <GameplaySummaryCard
            eyebrow="Business Summary"
            title={activeBusiness.business_name || businessLabel(activeBusiness.business_type)}
            subtitle={activeBusinessProfile
              ? `${activeBusinessProfile.growth_phase_label} operating from ${linkedAddress || activeBusinessProfile.location_label}`
              : (linkedAddress || activeBusiness.region_key || 'No lot linked yet')}
          >
            <SummaryStatRow
              business={activeBusiness}
              linkedAddress={linkedAddress}
              latestLog={latestLog}
              inventoryValueXgp={inventoryValueXgp}
            />

            <View style={styles.actionRow}>
              <PrimaryButton
                label={operatedToday ? 'Operated Today' : noInventory ? 'Buy Inventory First' : 'Run Business'}
                disabled={runDisabled}
                loading={loop.executingAction && canonicalActionKey(loop.busyActionKey || '') === 'operate_business'}
                onPress={() => { void loop.operateBusiness(); }}
                style={styles.actionButton}
              />
              <SecondaryButton
                label="Open Map Slot"
                onPress={() => onboarding.navigateTo('map')}
                style={styles.actionButton}
              />
            </View>
          </GameplaySummaryCard>

          <GameplaySummaryCard
            eyebrow="Inventory"
            title="Itemized stock on hand"
            subtitle="Every supplier item tracks quantity, average cost, retail, spoilage, and days of stock left."
          >
            <InventoryGrid items={inventoryItems} />
          </GameplaySummaryCard>

          <GameplaySummaryCard
            eyebrow="Supplier Market"
            title="Buy inventory before operating"
            subtitle={`Compatible supplier items for ${businessLabel(activeBusiness.business_type)}.`}
          >
            {supplierError ? (
              <GameplayWarningBanner
                title="Supplier market unavailable"
                message={supplierError}
                tone="danger"
              />
            ) : null}

            {supplierLoading ? (
              <Text style={styles.supportingCopy}>Loading supplier quotes...</Text>
            ) : (
              <View style={styles.supplierList}>
                {supplierItems.map((item) => {
                  const quantity = quantityByItem[item.item_id] || '';
                  const lineTotal = supplierQuantityValue(quantity) * Number(item.current_wholesale_cost || 0);
                  return (
                    <View key={item.item_id} style={styles.supplierCard}>
                      <View style={styles.supplierCardCopy}>
                        <Text style={styles.supplierTitle}>{item.display_name}</Text>
                        <Text style={styles.supplierMeta}>
                          Wholesale {formatMoney(Number(item.current_wholesale_cost || 0), 2)} | Retail {formatMoney(Number(item.current_retail_price || item.suggested_retail_price || 0), 2)}
                        </Text>
                        <Text style={styles.supplierMeta}>
                          {item.basket_link.replace(/_/g, ' ')} basket | Spoilage {(Number(item.spoilage_rate || 0) * 100).toFixed(0)}% | {item.unit_label}
                        </Text>
                      </View>
                      <View style={styles.supplierInputStack}>
                        <TextInput
                          value={quantity}
                          onChangeText={(value) => handleQuantityChange(item.item_id, value)}
                          keyboardType="number-pad"
                          placeholder="0"
                          placeholderTextColor={theme.ui.text.onDarkMuted}
                          style={styles.quantityInput}
                        />
                        <Text style={styles.lineTotalText}>{lineTotal > 0 ? formatMoney(lineTotal) : 'No order'}</Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            )}

            <View style={styles.purchaseFooter}>
              <View style={styles.purchaseFooterCopy}>
                <Text style={styles.purchaseTotalLabel}>Purchase total</Text>
                <Text style={styles.purchaseCashHint}>Cash on hand {formatMoney(cashOnHand)}</Text>
              </View>
              <Text style={styles.purchaseTotalValue}>{formatMoney(purchaseTotalXgp)}</Text>
            </View>

            <PrimaryButton
              label={purchaseBusy ? 'Buying Inventory...' : 'Buy Inventory'}
              onPress={() => { void handleBuyInventory(); }}
              disabled={!supplierItems.length || purchaseBusy}
              loading={purchaseBusy}
              style={styles.fullWidthButton}
            />
          </GameplaySummaryCard>

          <GameplaySummaryCard
            eyebrow="Daily Profit / Loss"
            title="Latest operating day breakdown"
            subtitle="Revenue, COGS, labor, overhead, spoilage, and stock-left all come from the backend daily log."
          >
            <DailyLogBreakdown latestLog={latestLog} />
          </GameplaySummaryCard>
        </>
      )}
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  metricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  actionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  actionButton: {
    flex: 1,
    minWidth: 150,
  },
  inventoryGrid: {
    gap: theme.spacing.sm,
  },
  inventoryCard: {
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    borderColor: theme.ui.border,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  inventoryCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  inventoryTitle: {
    ...theme.typography.headingSm,
    color: theme.ui.text.onDark,
    fontWeight: '800',
    flex: 1,
  },
  inventoryQuantity: {
    ...theme.typography.bodySm,
    color: theme.ui.info,
    fontWeight: '800',
  },
  inventoryMeta: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  supplierList: {
    gap: theme.spacing.sm,
  },
  supplierCard: {
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    borderColor: theme.ui.border,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  supplierCardCopy: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  supplierTitle: {
    ...theme.typography.headingSm,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  supplierMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '700',
  },
  supplierInputStack: {
    width: 108,
    alignItems: 'stretch',
    gap: theme.spacing.xs,
  },
  quantityInput: {
    minHeight: 46,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    borderColor: alpha(theme.ui.info, 0.32),
    backgroundColor: alpha(theme.ui.bg.card, 0.84),
    color: theme.ui.text.onDark,
    paddingHorizontal: theme.spacing.sm,
    ...theme.typography.bodyMd,
    fontWeight: '700',
    textAlign: 'center',
  },
  lineTotalText: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '800',
    textAlign: 'center',
  },
  purchaseFooter: {
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    borderColor: alpha(theme.ui.info, 0.24),
    backgroundColor: alpha(theme.ui.info, 0.08),
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  purchaseFooterCopy: {
    gap: 2,
  },
  purchaseTotalLabel: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  purchaseCashHint: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '700',
  },
  purchaseTotalValue: {
    ...theme.typography.headingSm,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  breakdownStack: {
    gap: theme.spacing.sm,
  },
  supportingCopy: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  warningText: {
    ...theme.typography.bodySm,
    color: theme.ui.warning,
    fontWeight: '700',
  },
  starterList: {
    gap: theme.spacing.sm,
  },
  starterCard: {
    backgroundColor: theme.color.surfaceAlt,
    borderColor: theme.color.border,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    gap: theme.spacing.xs,
    padding: theme.spacing.md,
  },
  starterTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
  },
  starterLine: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  needText: {
    color: theme.color.warning,
    fontWeight: '700',
  },
  readyText: {
    color: theme.color.positive,
    fontWeight: '700',
  },
  fullWidthButton: {
    width: '100%',
  },
});

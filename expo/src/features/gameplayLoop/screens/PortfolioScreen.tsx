import { useFocusEffect } from '@react-navigation/native';
import { router } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import MarketOverviewCard from '@/components/gameplay/MarketOverviewCard';
import PriceTrendsCard from '@/components/gameplay/PriceTrendsCard';
import StockMarketCard from '@/components/gameplay/StockMarketCard';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import PrimaryButton from '@/components/ui/PrimaryButton';
import { alpha, theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { getPortfolioSummary } from '@/lib/api/portfolio';
import { businessLabel, createEmptyBusinessSandboxState } from '@/lib/businessSandbox';
import { readBusinessSandboxState } from '@/lib/businessSandboxPersistence';
import {
  PortfolioSummary,
  mergePortfolioSummaryWithSandbox,
} from '@/lib/portfolioSummary';
import { formatMoney } from '@/lib/gameplayFormatters';

import { useGameplayLoop } from '../context';
import { GameplaySummaryCard } from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

function normalizeError(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  return 'Failed to load portfolio summary.';
}

function toneColor(value: number): string {
  if (value > 0) return theme.ui.positive;
  if (value < 0) return theme.ui.danger;
  return theme.color.textSecondary;
}

function fallbackPortfolioSummaryFromLoop(loop: ReturnType<typeof useGameplayLoop>): PortfolioSummary {
  const cash = Number(
    loop.authoritativeState?.player_state.cash
    ?? loop.dashboard?.stats.cash_xgp
    ?? 0,
  );
  const debt = Number(
    loop.authoritativeState?.player_state.debt
    ?? loop.dashboard?.stats.debt_xgp
    ?? 0,
  );
  const stockHoldingsValue = Number(loop.stockMarket?.portfolio.total_market_value_xgp || 0);
  const businessValue = Number(loop.businesses?.profit_snapshot.business_estimated_value_xgp || 0);
  const inventoryValue = Number(loop.businesses?.profit_snapshot.inventory_estimated_value_xgp || 0);
  const totalAssetsWithoutLand = cash + stockHoldingsValue + businessValue + inventoryValue;
  const businesses = (loop.businesses?.businesses || []).map((business) => ({
    business_id: String(business.business_id || ''),
    business_type: String(business.business_type || ''),
    region: business.region_key || null,
    linked_slot_id: null,
    address: null,
    reputation: Number(business.reputation || 0),
    inventory_value: Number(business.inventory_estimated_value_xgp || 0),
    avg_7_day_profit: Number(business.average_last_7_day_profit_xgp || 0),
    estimated_business_value: Number(business.business_estimated_value_xgp || 0),
    last_net_profit: Number(business.latest_daily_log?.net_profit_xgp || 0),
    last_operated_day: business.last_operated_day ?? null,
  })).filter((business) => business.business_id);

  return {
    player_id: loop.playerId,
    day: Number(loop.authoritativeState?.day_number ?? 1),
    cash,
    debt,
    stock_holdings_value: stockHoldingsValue,
    land_value: 0,
    business_value: businessValue,
    inventory_value: inventoryValue,
    total_assets: totalAssetsWithoutLand,
    net_worth: totalAssetsWithoutLand - debt,
    total_assets_without_sandbox_land: totalAssetsWithoutLand,
    net_worth_without_sandbox_land: totalAssetsWithoutLand - debt,
    latest_business_profit: Number(loop.businesses?.profit_snapshot.latest_daily_profit_xgp || 0),
    trailing_7d_business_profit: Number(loop.businesses?.profit_snapshot.trailing_7d_profit_xgp || 0),
    active_business_count: Number(
      loop.businesses?.profit_snapshot.active_businesses
      ?? loop.businesses?.businesses?.filter((business) => business.is_active).length
      ?? 0,
    ),
    owned_land: [],
    businesses,
  };
}

function MetricTile({ label, value, tone = 'neutral' }: {
  label: string;
  value: string;
  tone?: 'positive' | 'negative' | 'neutral';
}) {
  const color = tone === 'positive'
    ? theme.ui.positive
    : tone === 'negative'
      ? theme.ui.danger
      : theme.color.textPrimary;
  return (
    <View style={styles.metricTile}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color }]}>{value}</Text>
    </View>
  );
}

export default function PortfolioScreen() {
  useScreenTimer('portfolio');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const simplified = onboarding.isSimplifiedMode;
  const [sandboxBusinessState, setSandboxBusinessState] = useState(() => createEmptyBusinessSandboxState(loop.playerId));
  const [backendPortfolioSummary, setBackendPortfolioSummary] = useState<PortfolioSummary | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);

  useFocusEffect(useCallback(() => {
    let active = true;

    void Promise.allSettled([
      readBusinessSandboxState(loop.playerId),
      getPortfolioSummary(loop.playerId),
    ]).then(([sandboxResult, portfolioResult]) => {
      if (!active) return;

      if (sandboxResult.status === 'fulfilled') {
        setSandboxBusinessState(sandboxResult.value);
      }

      if (portfolioResult.status === 'fulfilled') {
        setBackendPortfolioSummary(portfolioResult.value);
        setPortfolioError(null);
      } else {
        setBackendPortfolioSummary(null);
        setPortfolioError(normalizeError(portfolioResult.reason));
      }
    });

    return () => {
      active = false;
    };
  }, [loop.playerId]));

  const fallbackSummary = useMemo(
    () => fallbackPortfolioSummaryFromLoop(loop),
    [loop],
  );

  const baseSummary = useMemo(() => {
    const source = backendPortfolioSummary || fallbackSummary;
    const liveCash = Number(
      loop.authoritativeState?.player_state.cash
      ?? loop.dashboard?.stats.cash_xgp
      ?? source.cash,
    );
    const liveDebt = Number(
      loop.authoritativeState?.player_state.debt
      ?? loop.dashboard?.stats.debt_xgp
      ?? source.debt,
    );
    const liveStockValue = Number(loop.stockMarket?.portfolio.total_market_value_xgp ?? source.stock_holdings_value);
    const liveBusinessValue = Number(loop.businesses?.profit_snapshot.business_estimated_value_xgp ?? source.business_value);
    const liveInventoryValue = Number(loop.businesses?.profit_snapshot.inventory_estimated_value_xgp ?? source.inventory_value);
    const totalAssetsWithoutLand = liveCash + liveStockValue + liveBusinessValue + liveInventoryValue;

    return {
      ...source,
      cash: liveCash,
      debt: liveDebt,
      stock_holdings_value: liveStockValue,
      business_value: liveBusinessValue,
      inventory_value: liveInventoryValue,
      total_assets_without_sandbox_land: totalAssetsWithoutLand,
      net_worth_without_sandbox_land: totalAssetsWithoutLand - liveDebt,
      total_assets: totalAssetsWithoutLand,
      net_worth: totalAssetsWithoutLand - liveDebt,
      latest_business_profit: Number(loop.businesses?.profit_snapshot.latest_daily_profit_xgp ?? source.latest_business_profit),
      trailing_7d_business_profit: Number(loop.businesses?.profit_snapshot.trailing_7d_profit_xgp ?? source.trailing_7d_business_profit),
      active_business_count: Number(
        loop.businesses?.profit_snapshot.active_businesses
        ?? loop.businesses?.businesses?.filter((business) => business.is_active).length
        ?? source.active_business_count,
      ),
    };
  }, [
    backendPortfolioSummary,
    fallbackSummary,
    loop.authoritativeState?.player_state.cash,
    loop.authoritativeState?.player_state.debt,
    loop.businesses?.businesses,
    loop.businesses?.profit_snapshot.active_businesses,
    loop.businesses?.profit_snapshot.business_estimated_value_xgp,
    loop.businesses?.profit_snapshot.inventory_estimated_value_xgp,
    loop.businesses?.profit_snapshot.latest_daily_profit_xgp,
    loop.businesses?.profit_snapshot.trailing_7d_profit_xgp,
    loop.dashboard?.stats.cash_xgp,
    loop.dashboard?.stats.debt_xgp,
    loop.stockMarket?.portfolio.total_market_value_xgp,
  ]);

  const portfolioSummary = useMemo(
    () => mergePortfolioSummaryWithSandbox(baseSummary, sandboxBusinessState.owned_lots || []),
    [baseSummary, sandboxBusinessState.owned_lots],
  );

  const portfolioMetrics = useMemo(() => ({
    cashXgp: portfolioSummary.cash,
    ownedSlotCount: portfolioSummary.owned_land.length,
    builtSlotCount: portfolioSummary.owned_land.filter((land) => land.ownership_status.includes('built')).length,
    landValueXgp: portfolioSummary.land_value,
    landCostBasisXgp: portfolioSummary.owned_land.reduce((sum, land) => sum + Number(land.purchase_price || 0), 0),
    stockValueXgp: portfolioSummary.stock_holdings_value,
    businessValueXgp: portfolioSummary.business_value,
    inventoryValueXgp: portfolioSummary.inventory_value,
    debtXgp: portfolioSummary.debt,
    totalAssetsXgp: portfolioSummary.total_assets,
    netWorthXgp: portfolioSummary.net_worth,
    latestBusinessIncomeXgp: portfolioSummary.latest_business_profit,
    trailingBusinessIncomeXgp: portfolioSummary.trailing_7d_business_profit,
    activeBusinessCount: portfolioSummary.active_business_count,
  }), [portfolioSummary]);

  return (
    <GameplayLoopScaffold
      title="Portfolio"
      subtitle="Cash, land, business value, inventory, and net worth in one place"
      activeNavKey="portfolio"
    >
      <GameplaySummaryCard eyebrow="Net Worth" title="Asset Summary">
        <View style={styles.netWorthCard}>
          <View style={styles.netWorthCopy}>
            <Text style={styles.netWorthLabel}>Total assets</Text>
            <Text style={styles.netWorthValue}>{formatMoney(portfolioSummary.total_assets)}</Text>
            <Text style={styles.netWorthMeta}>
              Debt {formatMoney(portfolioSummary.debt)} | Net worth {formatMoney(portfolioSummary.net_worth)}
            </Text>
          </View>
          <View style={styles.netWorthBadge}>
            <Text style={[styles.netWorthBadgeValue, { color: toneColor(portfolioSummary.net_worth) }]}>
              {formatMoney(portfolioSummary.net_worth)}
            </Text>
            <Text style={styles.netWorthBadgeLabel}>Net Worth</Text>
          </View>
        </View>

        <View style={styles.metricGrid}>
          <MetricTile label="Cash" value={formatMoney(portfolioSummary.cash)} />
          <MetricTile label="Stocks" value={formatMoney(portfolioSummary.stock_holdings_value)} />
          <MetricTile label="Land / Slots" value={formatMoney(portfolioSummary.land_value)} />
          <MetricTile label="Businesses" value={formatMoney(portfolioSummary.business_value)} />
          <MetricTile label="Inventory" value={formatMoney(portfolioSummary.inventory_value)} />
          <MetricTile
            label="Debt"
            value={formatMoney(portfolioSummary.debt)}
            tone={portfolioSummary.debt > 0 ? 'negative' : 'neutral'}
          />
        </View>

        {portfolioError ? (
          <Text style={styles.warningText}>Portfolio endpoint fallback active: {portfolioError}</Text>
        ) : null}

        <PrimaryButton
          testID="portfolio-timeline-button"
          label="View Timeline"
          onPress={() => router.push(`/gameplay/loop/${loop.playerId}/timeline`)}
        />
      </GameplaySummaryCard>

      <GameplaySummaryCard eyebrow="Owned Land" title="Slots & Land">
        {portfolioSummary.owned_land.length ? (
          <View style={styles.list}>
            {portfolioSummary.owned_land.map((land) => {
              const gainLoss = Number(land.current_value || 0) - Number(land.purchase_price || 0);
              return (
                <View key={land.slot_id} style={styles.itemRow}>
                  <View style={styles.itemHeader}>
                    <View style={styles.itemHeaderCopy}>
                      <Text style={styles.itemTitle}>{land.address}</Text>
                      <Text style={styles.itemMeta}>
                        {land.district || 'Unknown district'} | {land.region || 'Unknown region'}
                      </Text>
                    </View>
                    <View style={styles.valueBox}>
                      <Text style={styles.valueBoxLabel}>Current Value</Text>
                      <Text style={styles.valueBoxValue}>{formatMoney(land.current_value)}</Text>
                    </View>
                  </View>

                  <View style={styles.metricGrid}>
                    <MetricTile label="Purchase" value={formatMoney(land.purchase_price)} />
                    <MetricTile
                      label="Gain / Loss"
                      value={formatMoney(gainLoss)}
                      tone={gainLoss > 0 ? 'positive' : gainLoss < 0 ? 'negative' : 'neutral'}
                    />
                    <MetricTile label="Demand" value={String(Math.round(Number(land.demand_score || 0)))} />
                    <MetricTile label="Traffic" value={String(Math.round(Number(land.foot_traffic_score || 0)))} />
                    <MetricTile label="Risk" value={String(Math.round(Number(land.risk_score || 0)))} />
                    <MetricTile label="Best Fit" value={businessLabel(land.best_business_fit || 'either')} />
                  </View>

                  <Text style={styles.supportingCopy}>
                    {land.slot_type ? `${land.slot_type.replace(/_/g, ' ')} lot` : 'Owned lot'}
                    {land.linked_business_type ? ` | ${businessLabel(land.linked_business_type)}` : ''}
                    {land.ownership_status ? ` | ${land.ownership_status.replace(/_/g, ' ')}` : ''}
                  </Text>
                </View>
              );
            })}
          </View>
        ) : (
          <EmptyStateView
            title="No owned land yet"
            subtitle="Purchased slots will appear here with address, value, and linked business details."
          />
        )}
      </GameplaySummaryCard>

      <GameplaySummaryCard eyebrow="Businesses" title="Estimated Value">
        {portfolioSummary.businesses.length ? (
          <View style={styles.list}>
            {portfolioSummary.businesses.map((business) => (
              <View key={business.business_id} style={styles.itemRow}>
                <View style={styles.itemHeader}>
                  <View style={styles.itemHeaderCopy}>
                    <Text style={styles.itemTitle}>{businessLabel(business.business_type)}</Text>
                    <Text style={styles.itemMeta}>
                      {business.address || business.region || 'No linked address yet'}
                    </Text>
                  </View>
                  <View style={styles.valueBox}>
                    <Text style={styles.valueBoxLabel}>Estimated Value</Text>
                    <Text style={styles.valueBoxValue}>{formatMoney(business.estimated_business_value)}</Text>
                  </View>
                </View>

                <View style={styles.metricGrid}>
                  <MetricTile label="Inventory" value={formatMoney(business.inventory_value)} />
                  <MetricTile
                    label="Avg 7D Profit"
                    value={formatMoney(business.avg_7_day_profit)}
                    tone={business.avg_7_day_profit > 0 ? 'positive' : business.avg_7_day_profit < 0 ? 'negative' : 'neutral'}
                  />
                  <MetricTile
                    label="Last Profit"
                    value={formatMoney(business.last_net_profit)}
                    tone={business.last_net_profit > 0 ? 'positive' : business.last_net_profit < 0 ? 'negative' : 'neutral'}
                  />
                </View>

                <Text style={styles.supportingCopy}>
                  Reputation {business.reputation}
                  {business.last_operated_day != null ? ` | Last operated day ${business.last_operated_day}` : ''}
                </Text>
              </View>
            ))}
          </View>
        ) : (
          <EmptyStateView
            title="No businesses yet"
            subtitle="Opened businesses will show estimated value, inventory value, and recent profit here."
          />
        )}
      </GameplaySummaryCard>

      {loop.economySummary ? (
        <OnboardingHighlight target="market-price-movement">
          <GameplaySummaryCard eyebrow="Baskets" title="Price Trends">
            <MarketOverviewCard overview={loop.economySummary.market_overview} />
            <PriceTrendsCard trends={loop.economySummary.price_trends} />
          </GameplaySummaryCard>
        </OnboardingHighlight>
      ) : (
        <EmptyStateView
          title="Economy snapshot unavailable"
          subtitle="Refresh to load market and basket movement."
        />
      )}

      {!simplified && loop.stockMarket ? (
        <GameplaySummaryCard eyebrow="Holdings" title="Stock Exposure">
          <StockMarketCard
            market={loop.stockMarket}
            portfolioMetrics={portfolioMetrics}
          />
        </GameplaySummaryCard>
      ) : null}
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  netWorthCard: {
    borderWidth: 1,
    borderColor: alpha(theme.ui.info, 0.32),
    borderRadius: theme.radius.xl,
    backgroundColor: alpha(theme.ui.info, 0.08),
    padding: theme.spacing.md,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: theme.spacing.md,
  },
  netWorthCopy: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  netWorthLabel: {
    ...theme.typography.caption,
    color: theme.ui.info,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  netWorthValue: {
    ...theme.typography.headingMd,
    color: theme.color.textPrimary,
    fontWeight: '900',
  },
  netWorthMeta: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  netWorthBadge: {
    minWidth: 118,
    borderWidth: 1,
    borderColor: alpha(theme.ui.info, 0.36),
    borderRadius: theme.radius.md,
    backgroundColor: alpha(theme.ui.bg.cardRaised, 0.92),
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    alignItems: 'center',
  },
  netWorthBadgeValue: {
    ...theme.typography.bodyMd,
    fontWeight: '900',
  },
  netWorthBadgeLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  metricGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  metricTile: {
    flex: 1,
    minWidth: 110,
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  metricLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  metricValue: {
    ...theme.typography.bodyMd,
    fontWeight: '800',
  },
  warningText: {
    ...theme.typography.bodySm,
    color: theme.ui.warning,
    fontWeight: '700',
  },
  list: {
    gap: theme.spacing.sm,
  },
  itemRow: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: theme.spacing.sm,
  },
  itemHeaderCopy: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  itemTitle: {
    ...theme.typography.headingSm,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  itemMeta: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  valueBox: {
    minWidth: 116,
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.ui.bg.card,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    alignItems: 'center',
  },
  valueBoxLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  valueBoxValue: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  supportingCopy: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
});

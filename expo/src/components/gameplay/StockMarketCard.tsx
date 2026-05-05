import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';
import { formatMoney } from '@/lib/gameplayFormatters';
import { StockMarketItem, StockMarketSnapshotResponse } from '@/types/stocks';

interface PortfolioMetrics {
  cashXgp: number;
  stockValueXgp: number;
  ownedSlotCount: number;
  builtSlotCount: number;
  landValueXgp: number;
  landCostBasisXgp: number;
  businessValueXgp: number;
  inventoryValueXgp: number;
  debtXgp: number;
  totalAssetsXgp: number;
  netWorthXgp: number;
  latestBusinessIncomeXgp: number;
  trailingBusinessIncomeXgp: number;
  activeBusinessCount: number;
}

function changeTone(changePct: number): string {
  if (changePct > 0) return theme.ui.positive;
  if (changePct < 0) return theme.ui.danger;
  return theme.color.textSecondary;
}

function volatilityLabelText(label: StockMarketItem['volatility_label']): string {
  if (label === 'hot') return 'Hot';
  if (label === 'active') return 'Active';
  return 'Steady';
}

export default function StockMarketCard({
  market,
  portfolioMetrics,
}: {
  market: StockMarketSnapshotResponse;
  portfolioMetrics?: PortfolioMetrics;
}) {
  const hasStocks = market.stocks.length > 0;
  const hasHoldings = market.portfolio.holdings_count > 0;

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <View style={styles.headerCopy}>
          <Text style={styles.kicker}>Portfolio exposure</Text>
          <Text style={styles.heading}>Stock Holdings</Text>
          <Text style={styles.meta}>
            Day {market.latest_day ?? '?'} close pricing only. V1 shows holdings and movement without trading controls.
          </Text>
        </View>
        <View style={styles.summaryPill}>
          <Text style={styles.summaryPillLabel}>Held</Text>
          <Text style={styles.summaryPillValue}>{market.portfolio.holdings_count}</Text>
        </View>
      </View>

      <View style={styles.guidanceBox}>
        <Text style={styles.guidanceTitle}>Quick read</Text>
        <Text style={styles.guidanceText}>Stocks are read-only in V1. Cash, debt, land, business value, and inventory remain the core portfolio decisions.</Text>
      </View>

      {portfolioMetrics ? (
        <View style={styles.assetSnapshot}>
          <View style={styles.assetSnapshotHeader}>
            <View>
              <Text style={styles.assetSnapshotKicker}>Portfolio snapshot</Text>
              <Text style={styles.assetSnapshotTitle}>Total assets across cash, land, business, and inventory</Text>
            </View>
            <View style={styles.assetBadge}>
              <Text
                style={[
                  styles.assetBadgeValue,
                  { color: changeTone(portfolioMetrics.netWorthXgp) },
                ]}
              >
                {formatMoney(portfolioMetrics.netWorthXgp)}
              </Text>
              <Text style={styles.assetBadgeLabel}>Net Worth</Text>
            </View>
          </View>

          <View style={styles.portfolioGrid}>
            <View style={styles.portfolioTile}>
              <Text style={styles.tileLabel}>Cash</Text>
              <Text style={styles.tileValue}>{formatMoney(portfolioMetrics.cashXgp)}</Text>
            </View>
            <View style={styles.portfolioTile}>
              <Text style={styles.tileLabel}>Stocks</Text>
              <Text style={styles.tileValue}>{formatMoney(portfolioMetrics.stockValueXgp)}</Text>
            </View>
            <View style={styles.portfolioTile}>
              <Text style={styles.tileLabel}>Land / Slots</Text>
              <Text style={styles.tileValue}>{formatMoney(portfolioMetrics.landValueXgp)}</Text>
            </View>
            <View style={styles.portfolioTile}>
              <Text style={styles.tileLabel}>Businesses</Text>
              <Text style={styles.tileValue}>{formatMoney(portfolioMetrics.businessValueXgp)}</Text>
            </View>
            <View style={styles.portfolioTile}>
              <Text style={styles.tileLabel}>Inventory</Text>
              <Text style={styles.tileValue}>{formatMoney(portfolioMetrics.inventoryValueXgp)}</Text>
            </View>
            <View style={styles.portfolioTile}>
              <Text style={styles.tileLabel}>Debt</Text>
              <Text style={[styles.tileValue, { color: changeTone(-portfolioMetrics.debtXgp) }]}>
                {formatMoney(portfolioMetrics.debtXgp)}
              </Text>
            </View>
            <View style={styles.portfolioTile}>
              <Text style={styles.tileLabel}>Total Assets</Text>
              <Text style={styles.tileValue}>{formatMoney(portfolioMetrics.totalAssetsXgp)}</Text>
            </View>
            <View style={styles.portfolioTile}>
              <Text style={styles.tileLabel}>Latest Business</Text>
              <Text style={[styles.tileValue, { color: changeTone(portfolioMetrics.latestBusinessIncomeXgp) }]}>
                {formatMoney(portfolioMetrics.latestBusinessIncomeXgp)}
              </Text>
            </View>
            <View style={styles.portfolioTile}>
              <Text style={styles.tileLabel}>7D Business</Text>
              <Text style={[styles.tileValue, { color: changeTone(portfolioMetrics.trailingBusinessIncomeXgp) }]}>
                {formatMoney(portfolioMetrics.trailingBusinessIncomeXgp)}
              </Text>
            </View>
          </View>

          <Text style={styles.assetSnapshotHint}>
            Slots {portfolioMetrics.ownedSlotCount}, built sites {portfolioMetrics.builtSlotCount}, active businesses {portfolioMetrics.activeBusinessCount}. Land cost basis {formatMoney(portfolioMetrics.landCostBasisXgp)}.
          </Text>
        </View>
      ) : null}

      <View style={styles.portfolioGrid}>
        <View style={styles.portfolioTile}>
          <Text style={styles.tileLabel}>Cash</Text>
          <Text style={styles.tileValue}>{formatMoney(market.portfolio.available_cash_xgp)}</Text>
        </View>
        <View style={styles.portfolioTile}>
          <Text style={styles.tileLabel}>Held Market Value</Text>
          <Text style={styles.tileValue}>{formatMoney(market.portfolio.total_market_value_xgp)}</Text>
        </View>
        <View style={styles.portfolioTile}>
          <Text style={styles.tileLabel}>Unrealized P&L</Text>
          <Text style={[styles.tileValue, { color: changeTone(market.portfolio.total_unrealized_pnl_xgp) }]}>
            {formatMoney(market.portfolio.total_unrealized_pnl_xgp)}
          </Text>
        </View>
      </View>

      {!hasHoldings ? <Text style={styles.neutralHint}>No stock holdings yet.</Text> : null}

      {!hasStocks ? (
        <View style={styles.emptyBox}>
          <Text style={styles.emptyTitle}>Quotes unavailable</Text>
          <Text style={styles.emptyText}>No current stock quotes were returned. Refresh this section before making portfolio decisions.</Text>
        </View>
      ) : (
      <View style={styles.list}>
        {market.stocks.map((stock) => {
          return (
            <View key={stock.stock_id} style={styles.stockRow}>
              <View style={styles.stockHeader}>
                <View style={styles.stockTitleWrap}>
                  <Text style={styles.stockName}>{stock.stock_name}</Text>
                  <Text style={styles.stockMeta}>{stock.stock_id} • {stock.sector_key.replace(/_/g, ' ')}</Text>
                </View>
                <View style={styles.priceWrap}>
                  <Text style={styles.stockPrice}>{formatMoney(stock.current_price, 2)}</Text>
                  <Text style={[styles.stockChange, { color: changeTone(stock.daily_change_pct) }]}>
                    {stock.daily_change_pct > 0 ? '+' : ''}{stock.daily_change_pct.toFixed(2)}%
                  </Text>
                </View>
              </View>

              <View style={styles.signalRow}>
                <Text style={styles.signalText} numberOfLines={2}>{stock.sector_signal_summary}</Text>
                <View style={styles.volatilityBadge}>
                  <Text style={styles.volatilityBadgeText}>{volatilityLabelText(stock.volatility_label)}</Text>
                </View>
              </View>

              <View style={styles.holdingRow}>
                <View style={styles.holdingChip}>
                  <Text style={styles.holdingLabel}>Held</Text>
                  <Text style={styles.holdingValue}>{stock.holdings_quantity} share(s)</Text>
                </View>
                <View style={styles.holdingChip}>
                  <Text style={styles.holdingLabel}>Owned value</Text>
                  <Text style={styles.holdingValue}>{formatMoney(stock.holdings_market_value)}</Text>
                </View>
                <View style={styles.holdingChip}>
                  <Text style={styles.holdingLabel}>P&L</Text>
                  <Text style={[styles.holdingValue, { color: changeTone(stock.holdings_unrealized_pnl) }]}>{formatMoney(stock.holdings_unrealized_pnl)}</Text>
                </View>
              </View>

              <Text style={styles.actionHint} numberOfLines={2}>
                {stock.holdings_quantity > 0
                  ? 'Holding value is included in net worth.'
                  : 'Available quote only. Trading is outside V1.'}
              </Text>
            </View>
          );
        })}
      </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.color.surface,
    padding: theme.spacing.lg,
    gap: theme.spacing.lg,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: theme.spacing.sm,
  },
  headerCopy: {
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
  heading: {
    ...theme.typography.headingMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  meta: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  summaryPill: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    alignItems: 'center',
    minWidth: 72,
  },
  summaryPillLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  summaryPillValue: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  portfolioGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  portfolioTile: {
    flex: 1,
    minWidth: 110,
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  tileLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  tileValue: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  guidanceBox: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  guidanceTitle: {
    ...theme.typography.caption,
    color: theme.ui.info,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  guidanceText: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
  },
  assetSnapshot: {
    borderWidth: 1,
    borderColor: alpha(theme.ui.info, 0.32),
    borderRadius: theme.radius.xl,
    backgroundColor: alpha(theme.ui.info, 0.08),
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  assetSnapshotHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: theme.spacing.sm,
  },
  assetSnapshotKicker: {
    ...theme.typography.caption,
    color: theme.ui.info,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  assetSnapshotTitle: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  assetBadge: {
    minWidth: 112,
    borderWidth: 1,
    borderColor: alpha(theme.ui.info, 0.36),
    borderRadius: theme.radius.md,
    backgroundColor: alpha(theme.ui.bg.cardRaised, 0.92),
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    alignItems: 'center',
  },
  assetBadgeValue: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '900',
  },
  assetBadgeLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  assetSnapshotHint: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    fontWeight: '700',
  },
  neutralHint: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  list: {
    gap: theme.spacing.sm,
  },
  emptyBox: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.color.surfaceAlt,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  emptyTitle: {
    ...theme.typography.label,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  emptyText: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  stockRow: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  stockHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  stockTitleWrap: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  stockName: {
    ...theme.typography.headingSm,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  stockMeta: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  priceWrap: {
    alignItems: 'flex-end',
    gap: theme.spacing.xxs,
  },
  stockPrice: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  stockChange: {
    ...theme.typography.caption,
    fontWeight: '800',
  },
  signalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  signalText: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    flex: 1,
  },
  actionHint: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  volatilityBadge: {
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: theme.radius.pill,
    backgroundColor: alpha(theme.ui.info, 0.14),
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  volatilityBadgeText: {
    ...theme.typography.caption,
    color: theme.ui.info,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  holdingRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  holdingChip: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.card,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  holdingLabel: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  holdingValue: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
});

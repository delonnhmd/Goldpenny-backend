import { useFocusEffect } from '@react-navigation/native';
import React, { useCallback, useMemo, useState } from 'react';

import MarketOverviewCard from '@/components/gameplay/MarketOverviewCard';
import PriceTrendsCard from '@/components/gameplay/PriceTrendsCard';
import StockMarketCard from '@/components/gameplay/StockMarketCard';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { createEmptyBusinessSandboxState } from '@/lib/businessSandbox';
import { readBusinessSandboxState } from '@/lib/businessSandboxPersistence';

import { useGameplayLoop } from '../context';
import { GameplaySummaryCard } from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

export default function MarketScreen() {
  useScreenTimer('market');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const simplified = onboarding.isSimplifiedMode;
  const [sandboxBusinessState, setSandboxBusinessState] = useState(() => createEmptyBusinessSandboxState(loop.playerId));

  useFocusEffect(useCallback(() => {
    let active = true;
    void readBusinessSandboxState(loop.playerId).then((state) => {
      if (active) setSandboxBusinessState(state);
    });
    return () => {
      active = false;
    };
  }, [loop.playerId]));

  const portfolioMetrics = useMemo(() => {
    const ownedSlots = sandboxBusinessState.owned_lots || [];
    const businessSnapshot = loop.businesses?.profit_snapshot || {};
    const activeBusinessCount = Number(
      businessSnapshot.active_businesses
      ?? loop.businesses?.businesses?.filter((business) => business.is_active).length
      ?? 0,
    );

    return {
      currentCashXgp: Number(
        loop.authoritativeState?.player_state.cash
        ?? loop.dashboard?.stats.cash_xgp
        ?? loop.stockMarket?.portfolio.available_cash_xgp
        ?? 0,
      ),
      ownedSlotCount: ownedSlots.length,
      builtSlotCount: ownedSlots.filter((lot) => Boolean(lot.placed_business_id)).length,
      slotValueXgp: ownedSlots.reduce((sum, lot) => sum + Number(lot.value_xgp || lot.purchase_price_xgp || 0), 0),
      slotCostXgp: ownedSlots.reduce((sum, lot) => sum + Number(lot.purchase_price_xgp || 0), 0),
      latestBusinessIncomeXgp: Number(businessSnapshot.latest_daily_profit_xgp || 0),
      trailingBusinessIncomeXgp: Number(businessSnapshot.trailing_7d_profit_xgp || 0),
      activeBusinessCount,
    };
  }, [
    loop.authoritativeState?.player_state.cash,
    loop.businesses?.businesses,
    loop.businesses?.profit_snapshot,
    loop.dashboard?.stats.cash_xgp,
    loop.stockMarket?.portfolio.available_cash_xgp,
    sandboxBusinessState.owned_lots,
  ]);

  return (
    <GameplayLoopScaffold
      title="Market"
      subtitle="Read basket signals, then evaluate optional stock exposure"
      activeNavKey="market"
    >
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
        <GameplaySummaryCard eyebrow="Stocks" title="Stock Lane">
          <StockMarketCard
            market={loop.stockMarket}
            portfolioMetrics={portfolioMetrics}
            sessionActive={loop.dailySession.sessionStatus === 'active'}
            pendingTradeStockId={loop.pendingTrade?.stockId || null}
            pendingTradeSide={loop.pendingTrade?.side || null}
            onBuyOne={(stockId) => {
              void loop.buyOneStock(stockId);
            }}
            onSellOne={(stockId) => {
              void loop.sellOneStock(stockId);
            }}
            onSellAll={(stockId, quantity) => {
              void loop.sellAllStock(stockId, quantity);
            }}
          />
        </GameplaySummaryCard>
      ) : null}
    </GameplayLoopScaffold>
  );
}

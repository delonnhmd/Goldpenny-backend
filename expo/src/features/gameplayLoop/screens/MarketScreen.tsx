import React from 'react';

import MarketOverviewCard from '@/components/gameplay/MarketOverviewCard';
import PriceTrendsCard from '@/components/gameplay/PriceTrendsCard';
import StockMarketCard from '@/components/gameplay/StockMarketCard';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';

import { useGameplayLoop } from '../context';
import {
  GameplayStickyActionArea,
  GameplaySummaryCard,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

export default function MarketScreen() {
  useScreenTimer('market');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const guidedMarketActive = onboarding.isActive && onboarding.currentStep?.route === 'market';
  const simplified = onboarding.isSimplifiedMode;

  return (
    <GameplayLoopScaffold
      title="Market"
      subtitle="Read basket signals, then evaluate optional stock exposure"
      activeNavKey="market"
      footer={guidedMarketActive ? null : (
        <GameplayStickyActionArea
          secondaryLabel="Open Business"
          onSecondaryPress={() => { onboarding.navigateTo('business'); }}
          primaryLabel="Back To Dashboard"
          onPrimaryPress={() => { onboarding.navigateTo('dashboard'); }}
        />
      )}
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

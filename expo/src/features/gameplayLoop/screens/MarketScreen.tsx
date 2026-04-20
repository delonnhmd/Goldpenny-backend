import React from 'react';

import AnimatedMoneyValue from '@/components/motion/AnimatedMoneyValue';
import MarketOverviewCard from '@/components/gameplay/MarketOverviewCard';
import PriceTrendsCard from '@/components/gameplay/PriceTrendsCard';
import StockMarketCard from '@/components/gameplay/StockMarketCard';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { formatMoney } from '@/lib/gameplayFormatters';

import { useGameplayLoop } from '../context';
import {
  GameplayCompactMetricRows,
  GameplayStickyActionArea,
  GameplaySummaryCard,
  GameplayWarningBanner,
  toneFromSignedValue,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

function titleCase(value: string): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (!normalized) return 'Stable';
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export default function PortfolioScreen() {
  useScreenTimer('portfolio');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const guidedPortfolioActive = onboarding.isActive && onboarding.currentStep?.route === 'portfolio';
  const simplified = onboarding.isSimplifiedMode;
  const stats = loop.dashboard?.stats;
  const cash = Number(stats?.cash_xgp ?? 0);
  const debt = Number(loop.expenseDebt?.debtAmount ?? stats?.debt_xgp ?? 0);
  const netWorth = Number(stats?.net_worth_xgp ?? 0);
  const netFlow = Number(loop.economyState.netCashFlow ?? 0);
  const debtPressure = titleCase(loop.expenseDebt.debtPressure);
  const topRisk = loop.dashboard?.top_risks?.[0] || null;
  const topOpportunity = loop.dashboard?.top_opportunities?.[0] || null;

  return (
    <GameplayLoopScaffold
      title="Portfolio"
      subtitle="Cash, debt, net worth, and holdings in one capital view"
      activeNavKey="portfolio"
      footer={guidedPortfolioActive ? null : (
        <GameplayStickyActionArea
          secondaryLabel="Open Business"
          onSecondaryPress={() => { onboarding.navigateTo('business'); }}
          primaryLabel="Back To Work"
          onPrimaryPress={() => { onboarding.navigateTo('work'); }}
        />
      )}
    >
      <OnboardingHighlight target="portfolio-money-overview">
        <GameplaySummaryCard
          eyebrow="Money overview"
          title="Capital Position"
          subtitle="Financial widgets from the old dashboard now live here."
        >
          <GameplayCompactMetricRows
            items={[
              {
                label: 'Cash',
                value: formatMoney(cash),
                tone: cash > 0 ? 'positive' : cash < 0 ? 'danger' : 'neutral',
                valueNode: (
                  <AnimatedMoneyValue
                    value={cash}
                    tone={cash > 0 ? 'positive' : cash < 0 ? 'danger' : 'neutral'}
                    threshold={0.1}
                    durationMs={700}
                  />
                ),
              },
              {
                label: 'Net cash flow',
                value: `${netFlow > 0 ? '+' : ''}${formatMoney(netFlow)}`,
                tone: toneFromSignedValue(netFlow),
              },
              { label: 'Net worth', value: formatMoney(netWorth), tone: netWorth >= 0 ? 'positive' : 'warning' },
              { label: 'Debt', value: formatMoney(debt), tone: debt > 0 ? 'warning' : 'positive' },
              { label: 'Debt pressure', value: debtPressure, tone: loop.expenseDebt.debtWarning ? 'danger' : 'neutral' },
            ]}
          />
          {topOpportunity ? (
            <GameplayWarningBanner
              title="Capital upside"
              message={topOpportunity.title}
              tone="info"
            />
          ) : null}
          {topRisk ? (
            <GameplayWarningBanner
              title="Capital pressure"
              message={topRisk.title}
              tone="warning"
            />
          ) : null}
        </GameplaySummaryCard>
      </OnboardingHighlight>

      {loop.economySummary ? (
        <GameplaySummaryCard eyebrow="Baskets" title="Economic Outlook">
            <MarketOverviewCard overview={loop.economySummary.market_overview} />
            <PriceTrendsCard trends={loop.economySummary.price_trends} />
        </GameplaySummaryCard>
      ) : (
        <EmptyStateView
          title="Economy snapshot unavailable"
          subtitle="Refresh to load market and basket movement."
        />
      )}

      {!simplified && loop.stockMarket ? (
        <GameplaySummaryCard eyebrow="Holdings" title="Stock Lane">
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

import { BusinessPlanResponse } from '@/types/strategicPlanning';
import { PlayerBusinessesResponse } from '@/types/business';
import { EconomyPresentationSummaryResponse } from '@/types/economyPresentation';
import {
  DailyActionHubResponse,
  EndOfDaySummaryResponse,
  PlayerDashboardResponse,
} from '@/types/gameplay';
import { StockMarketSnapshotResponse } from '@/types/stocks';

export type GameplayLoopDataMode = 'live' | 'mixed' | 'mock';

export interface GameplayLoopDataSource {
  mode: GameplayLoopDataMode;
  notes: string[];
}

export interface GameplayLoopBundle {
  playerId: string;
  dashboard: PlayerDashboardResponse;
  actionHub: DailyActionHubResponse;
  economySummary: EconomyPresentationSummaryResponse;
  stockMarket: StockMarketSnapshotResponse;
  businesses: PlayerBusinessesResponse;
  businessPlan: BusinessPlanResponse;
  endOfDaySummary: EndOfDaySummaryResponse | null;
  source: GameplayLoopDataSource;
  fetchedAt: string;
}

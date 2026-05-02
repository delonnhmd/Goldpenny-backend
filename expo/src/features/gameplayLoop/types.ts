import { BusinessPlanResponse } from '@/types/strategicPlanning';
import { PlayerBusinessesResponse } from '@/types/business';
import { EconomyPresentationSummaryResponse } from '@/types/economyPresentation';
import {
  AbsenceSummary,
  DailyActionHubResponse,
  EndOfDaySummaryResponse,
  GameTimePayload,
  GameplayAuthoritativeState,
  PlayerRunStatusResponse,
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
  gameTime: GameTimePayload | null;
  runStatus: PlayerRunStatusResponse | null;
  actionHub: DailyActionHubResponse;
  authoritativeState: GameplayAuthoritativeState | null;
  economySummary: EconomyPresentationSummaryResponse;
  stockMarket: StockMarketSnapshotResponse;
  businesses: PlayerBusinessesResponse;
  businessPlan: BusinessPlanResponse;
  endOfDaySummary: EndOfDaySummaryResponse | null;
  absenceSummary: AbsenceSummary | null;
  source: GameplayLoopDataSource;
  fetchedAt: string;
}

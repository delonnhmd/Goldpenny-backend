import { getPlayerBusinesses } from '@/lib/api/business';
import {
  getEndOfDaySummary,
  getPlayerActions,
  getPlayerDashboard,
  previewPlayerAction,
} from '@/lib/api/gameplay';
import { getEconomyPresentationSummary } from '@/lib/api/economyPresentation';
import { getStockMarketSnapshot } from '@/lib/api/stocks';
import { getBusinessPlan } from '@/lib/api/strategicPlanning';
import { recordInfo, recordWarning } from '@/lib/logger';
import { ActionPreviewRequest, ActionPreviewResponse, EndOfDaySummaryResponse } from '@/types/gameplay';

import {
  createMockActionHub,
  createMockActionPreview,
  createMockBusinessPlan,
  createMockBusinesses,
  createMockDashboard,
  createMockEconomySummary,
  createMockStockMarket,
} from './mockData';
import { GameplayLoopBundle, GameplayLoopDataMode } from './types';

interface LoadGameplayLoopBundleOptions {
  includeEndOfDaySummary?: boolean;
}

interface ResolvedSection<T> {
  value: T;
  usedMock: boolean;
  note: string | null;
}

function normalizeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

async function resolveSection<T>(
  playerId: string,
  section: string,
  loader: () => Promise<T>,
  mockFactory: () => T,
): Promise<ResolvedSection<T>> {
  try {
    const value = await loader();
    return {
      value,
      usedMock: false,
      note: null,
    };
  } catch (error) {
    const reason = normalizeError(error);
    recordWarning('gameplayLoop', `Falling back to mock ${section}.`, {
      action: 'resolve_section',
      context: {
        playerId,
        section,
      },
      error,
    });
    return {
      value: mockFactory(),
      usedMock: true,
      note: `${section}: ${reason}`,
    };
  }
}

async function resolveOptionalSection<T>(
  playerId: string,
  section: string,
  loader: () => Promise<T>,
): Promise<ResolvedSection<T | null>> {
  try {
    const value = await loader();
    return {
      value,
      usedMock: false,
      note: null,
    };
  } catch (error) {
    const reason = normalizeError(error);
    recordInfo('gameplayLoop', `Optional section unavailable: ${section}.`, {
      action: 'resolve_optional_section',
      context: {
        playerId,
        section,
        reason,
      },
    });
    return {
      value: null,
      usedMock: false,
      note: `${section}: ${reason}`,
    };
  }
}

function deriveSourceMode(mockCount: number, totalCount: number): GameplayLoopDataMode {
  if (mockCount <= 0) return 'live';
  if (mockCount >= totalCount) return 'mock';
  return 'mixed';
}

export async function loadGameplayLoopBundle(
  playerId: string,
  options?: LoadGameplayLoopBundleOptions,
): Promise<GameplayLoopBundle> {
  const includeEndOfDaySummary = Boolean(options?.includeEndOfDaySummary);

  const [dashboard, actionHub, economySummary, stockMarket, businesses, businessPlan, endOfDaySummary] =
    await Promise.all([
      resolveSection(playerId, 'dashboard', () => getPlayerDashboard(playerId), () => createMockDashboard(playerId)),
      resolveSection(playerId, 'action_hub', () => getPlayerActions(playerId), () => createMockActionHub(playerId)),
      resolveSection(
        playerId,
        'economy_summary',
        () => getEconomyPresentationSummary(playerId),
        () => createMockEconomySummary(playerId),
      ),
      resolveSection(
        playerId,
        'stock_market',
        () => getStockMarketSnapshot(playerId),
        () => createMockStockMarket(playerId),
      ),
      resolveSection(
        playerId,
        'business_summary',
        () => getPlayerBusinesses(playerId),
        () => createMockBusinesses(playerId),
      ),
      resolveSection(
        playerId,
        'business_plan',
        () => getBusinessPlan(playerId),
        () => createMockBusinessPlan(playerId),
      ),
      includeEndOfDaySummary
        ? resolveOptionalSection(
          playerId,
          'end_of_day_summary',
          () => getEndOfDaySummary(playerId),
        )
        : Promise.resolve<ResolvedSection<EndOfDaySummaryResponse | null>>({
          value: null,
          usedMock: false,
          note: null,
        }),
    ]);

  const sourceSections = [dashboard, actionHub, economySummary, stockMarket, businesses, businessPlan];
  const mockCount = sourceSections.filter((entry) => entry.usedMock).length;
  const notes = [...sourceSections, endOfDaySummary]
    .map((entry) => entry.note)
    .filter((entry): entry is string => Boolean(entry));

  recordInfo('gameplayLoop', 'End-of-day summary gate evaluated.', {
    action: 'summary_gate',
    context: {
      playerId,
      includeEndOfDaySummary,
      summaryExists: Boolean(endOfDaySummary.value),
      summaryNote: endOfDaySummary.note,
    },
  });

  return {
    playerId,
    dashboard: dashboard.value,
    actionHub: actionHub.value,
    economySummary: economySummary.value,
    stockMarket: stockMarket.value,
    businesses: businesses.value,
    businessPlan: businessPlan.value,
    endOfDaySummary: endOfDaySummary.value,
    source: {
      mode: deriveSourceMode(mockCount, sourceSections.length),
      notes,
    },
    fetchedAt: new Date().toISOString(),
  };
}

export async function loadActionPreviewWithFallback(
  playerId: string,
  payload: ActionPreviewRequest,
): Promise<{ preview: ActionPreviewResponse; usedMock: boolean; note: string | null }> {
  try {
    const preview = await previewPlayerAction(playerId, payload);
    return { preview, usedMock: false, note: null };
  } catch (error) {
    return {
      preview: createMockActionPreview(playerId, payload),
      usedMock: true,
      note: `action_preview: ${normalizeError(error)}`,
    };
  }
}

export async function loadEndOfDaySummaryWithFallback(
  playerId: string,
): Promise<{ summary: EndOfDaySummaryResponse | null; usedMock: boolean; note: string | null }> {
  try {
    const summary = await getEndOfDaySummary(playerId);
    return {
      summary,
      usedMock: false,
      note: null,
    };
  } catch (error) {
    const reason = normalizeError(error);
    recordInfo('gameplayLoop', 'End-of-day summary unavailable after settlement.', {
      action: 'summary_missing_after_settlement',
      context: {
        playerId,
        reason,
      },
    });
    return {
      summary: null,
      usedMock: false,
      note: `end_of_day_summary: ${reason}`,
    };
  }
}

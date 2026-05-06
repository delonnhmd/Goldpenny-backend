import { getPlayerBusinesses } from '@/lib/api/business';
import {
  getEndOfDaySummary,
  getGameTime,
  getPlayerLoopBundle,
  getPlayerRunStatus,
  previewPlayerAction,
} from '@/lib/api/gameplay';
import { getEconomyPresentationSummary } from '@/lib/api/economyPresentation';
import { getStockMarketSnapshot } from '@/lib/api/stocks';
import { recordInfo, recordWarning } from '@/lib/logger';
import { ActionPreviewRequest, ActionPreviewResponse, EndOfDaySummaryResponse } from '@/types/gameplay';

import {
  createMockActionHub,
  createMockActionPreview,
  createMockBusinesses,
  createMockDashboard,
  createMockEconomySummary,
  createMockStockMarket,
} from './mockData';
import { GameplayLoopBundle, GameplayLoopDataMode } from './types';

interface LoadGameplayLoopBundleOptions {
  includeEndOfDaySummary?: boolean;
  currentStress?: number | null;
  currentHealth?: number | null;
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

// Phase 4 blocker: mock fallbacks for live game data are restricted to dev
// builds. In production/V1, a failed backend section returns a safe empty
// state via `emptyFactory` instead of fake content.
const ALLOW_MOCK_FALLBACK_IN_DEV =
  typeof __DEV__ !== 'undefined' ? Boolean(__DEV__) : false;

async function resolveSection<T>(
  playerId: string,
  section: string,
  loader: () => Promise<T>,
  mockFactory: () => T,
  options?: { allowMockFallback?: boolean; emptyFactory?: () => T; isCritical?: boolean },
): Promise<ResolvedSection<T>> {
  const isCritical = options?.isCritical ?? false;
  const allowMockFallback =
    options?.allowMockFallback ?? (!isCritical && ALLOW_MOCK_FALLBACK_IN_DEV);
  const emptyFactory = options?.emptyFactory;
  try {
    const value = await loader();
    return {
      value,
      usedMock: false,
      note: null,
    };
  } catch (error) {
    const reason = normalizeError(error);
    if (isCritical) {
      recordWarning('gameplayLoop', `Critical section failed without fallback: ${section}.`, {
        action: 'resolve_section_critical_failure',
        context: {
          playerId,
          section,
          reason,
        },
        error,
      });
      throw new Error(`${section}: ${reason}`);
    }
    if (!allowMockFallback) {
      if (emptyFactory) {
        recordWarning('gameplayLoop', `Backend section unavailable; rendering empty safe state for ${section}.`, {
          action: 'resolve_section_empty_safe_state',
          context: { playerId, section, reason },
          error,
        });
        return {
          value: emptyFactory(),
          usedMock: false,
          note: `${section}: ${reason}`,
        };
      }
      throw new Error(`${section}: ${reason}`);
    }
    recordWarning('gameplayLoop', `[dev-only] Falling back to mock ${section}.`, {
      action: 'resolve_section_dev_mock',
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

function emptyEconomySummary(playerId: string) {
  return {
    player_id: playerId,
    as_of_day: 0,
    macro_state: null,
    economy_pulse: null,
    sectors: [],
    player_warnings: [],
    player_opportunities: [],
    debug_meta: { source: 'empty_safe_state' },
  } as ReturnType<typeof createMockEconomySummary>;
}

function emptyStockMarket(playerId: string) {
  return {
    player_id: playerId,
    as_of_day: 0,
    market_open: false,
    indices: [],
    sectors: [],
    movers_up: [],
    movers_down: [],
    holdings: [],
    debug_meta: { source: 'empty_safe_state' },
  } as ReturnType<typeof createMockStockMarket>;
}

function emptyBusinesses(playerId: string) {
  return {
    player_id: playerId,
    businesses: [],
    profit_snapshot: {
      player_id: playerId,
      day: 0,
      total_businesses: 0,
      active_businesses: 0,
      latest_daily_profit_xgp: 0,
      trailing_7d_profit_xgp: 0,
      inventory_estimated_value_xgp: 0,
      business_estimated_value_xgp: 0,
      business_type_breakdown: [],
    },
  } as ReturnType<typeof createMockBusinesses>;
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
  const gameplayStateOverrides = {
    currentStress: options?.currentStress,
    currentHealth: options?.currentHealth,
  };

  const [coreLoop, gameTime, runStatus, economySummary, stockMarket, businesses, endOfDaySummary] =
    await Promise.all([
      resolveSection(
        playerId,
        'loop_core',
        () => getPlayerLoopBundle(playerId, gameplayStateOverrides),
        () => ({
          player_id: playerId,
          dashboard: createMockDashboard(playerId),
          action_hub: createMockActionHub(playerId),
          authoritative_state: null,
          debug_meta: {},
        }),
        { isCritical: true },
      ),
      resolveOptionalSection(
        playerId,
        'game_time',
        () => getGameTime(),
      ),
      resolveOptionalSection(
        playerId,
        'run_status',
        () => getPlayerRunStatus(playerId),
      ),
      resolveSection(
        playerId,
        'economy_summary',
        () => getEconomyPresentationSummary(playerId),
        () => createMockEconomySummary(playerId),
        { emptyFactory: () => emptyEconomySummary(playerId) },
      ),
      resolveSection(
        playerId,
        'stock_market',
        () => getStockMarketSnapshot(playerId),
        () => createMockStockMarket(playerId),
        { emptyFactory: () => emptyStockMarket(playerId) },
      ),
      resolveSection(
        playerId,
        'business_summary',
        () => getPlayerBusinesses(playerId),
        () => createMockBusinesses(playerId),
        { emptyFactory: () => emptyBusinesses(playerId) },
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

  const sourceSections = [coreLoop, economySummary, stockMarket, businesses];
  const mockCount = sourceSections.filter((entry) => entry.usedMock).length;
  const notes = [...sourceSections, gameTime, runStatus, endOfDaySummary]
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
    dashboard: coreLoop.value.dashboard,
    gameTime: gameTime.value || coreLoop.value.game_time || coreLoop.value.dashboard.game_time || null,
    runStatus: runStatus.value || coreLoop.value.run_status || coreLoop.value.dashboard.run_status || null,
    actionHub: coreLoop.value.action_hub,
    authoritativeState: coreLoop.value.authoritative_state || null,
    economySummary: economySummary.value,
    stockMarket: stockMarket.value,
    businesses: businesses.value,
    endOfDaySummary: endOfDaySummary.value,
    absenceSummary: coreLoop.value.absence_summary || null,
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
    if (!ALLOW_MOCK_FALLBACK_IN_DEV) {
      throw new Error(`action_preview: ${normalizeError(error)}`);
    }
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

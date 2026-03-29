import { fetchApi } from '@/lib/apiClient';
import {
  LocalPressureSummaryResponse,
  PlayerPatternSummaryResponse,
  RegionMemorySummaryResponse,
  WorldMemoryHistoryResponse,
  WorldMemorySnapshotResponse,
  WorldMemorySummaryResponse,
  WorldNarrativeResponse,
  WorldPatternsResponse,
} from '@/types/worldMemory';


function toResponseDateValue(asOfDate?: string | null): string {
  if (!asOfDate) return '';
  return encodeURIComponent(asOfDate);
}

function withDateParam(path: string, asOfDate?: string | null): string {
  const dateValue = toResponseDateValue(asOfDate);
  if (!dateValue) return path;
  return `${path}?as_of_date=${dateValue}`;
}

export async function getWorldMemorySnapshot(
  playerId: string,
  asOfDate?: string | null,
): Promise<WorldMemorySnapshotResponse> {
  return fetchApi<WorldMemorySnapshotResponse>(
    withDateParam(`/world-memory/player/${playerId}/snapshot`, asOfDate),
  );
}

export async function getWorldMemoryPatterns(
  playerId: string,
  asOfDate?: string | null,
): Promise<WorldPatternsResponse> {
  return fetchApi<WorldPatternsResponse>(
    withDateParam(`/world-memory/player/${playerId}/patterns`, asOfDate),
  );
}

export async function getWorldNarrative(
  playerId: string,
  asOfDate?: string | null,
): Promise<WorldNarrativeResponse> {
  return fetchApi<WorldNarrativeResponse>(
    withDateParam(`/world-memory/player/${playerId}/narrative`, asOfDate),
  );
}

export async function getLocalPressure(
  playerId: string,
  asOfDate?: string | null,
): Promise<LocalPressureSummaryResponse> {
  return fetchApi<LocalPressureSummaryResponse>(
    withDateParam(`/world-memory/player/${playerId}/local-pressure`, asOfDate),
  );
}

export async function getPlayerPatterns(
  playerId: string,
  asOfDate?: string | null,
): Promise<PlayerPatternSummaryResponse> {
  return fetchApi<PlayerPatternSummaryResponse>(
    withDateParam(`/world-memory/player/${playerId}/player-patterns`, asOfDate),
  );
}

export async function getRegionMemory(
  playerId: string,
  asOfDate?: string | null,
): Promise<RegionMemorySummaryResponse> {
  return fetchApi<RegionMemorySummaryResponse>(
    withDateParam(`/world-memory/player/${playerId}/region-memory`, asOfDate),
  );
}

export async function getWorldMemoryHistory(
  playerId: string,
  asOfDate?: string | null,
  limit = 30,
): Promise<WorldMemoryHistoryResponse> {
  const basePath = withDateParam(`/world-memory/player/${playerId}/history`, asOfDate);
  const separator = basePath.includes('?') ? '&' : '?';
  const path = `${basePath}${separator}limit=${Math.max(1, Math.min(200, Number(limit) || 30))}`;
  return fetchApi<WorldMemoryHistoryResponse>(path);
}

export async function getWorldMemorySummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<WorldMemorySummaryResponse> {
  return fetchApi<WorldMemorySummaryResponse>(
    withDateParam(`/world-memory/player/${playerId}/summary`, asOfDate),
  );
}

export async function refreshWorldMemory(
  playerId: string,
  asOfDate?: string | null,
): Promise<WorldMemorySnapshotResponse> {
  return fetchApi<WorldMemorySnapshotResponse>(
    withDateParam(`/world-memory/player/${playerId}/refresh`, asOfDate),
    { method: 'POST' },
  );
}

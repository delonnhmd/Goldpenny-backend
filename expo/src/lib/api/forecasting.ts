// Step 42 — Forecasting, Planning Intelligence, and Forward Projection Layer API client

import { fetchApi } from '@/lib/apiClient';
import {
  DecisionGuidanceResponse,
  ForecastSnapshotResponse,
  ForecastSummaryResponse,
  RiskProjectionResponse,
  ScenarioComparisonRequest,
  ScenarioComparisonResponse,
  ShortTermForecastResponse,
  SimulationRequest,
  SimulationResponse,
} from '@/types/forecasting';


function dayParam(day?: number, extraParams?: string): string {
  const parts: string[] = [];
  if (day !== undefined) parts.push(`day=${day}`);
  if (extraParams) parts.push(extraParams);
  return parts.length ? `?${parts.join('&')}` : '';
}

// ---------------------------------------------------------------------------
// 1. Short-term cash-flow forecast
// ---------------------------------------------------------------------------

export async function getShortTermForecast(
  playerId: string,
  day?: number,
  horizonDays: number = 14,
): Promise<ShortTermForecastResponse> {
  const extra = `horizon_days=${horizonDays}`;
  return fetchApi(`/forecast/player/${playerId}/short-term${dayParam(day, extra)}`);
}

// ---------------------------------------------------------------------------
// 2. Risk projection / danger radar
// ---------------------------------------------------------------------------

export async function getRiskProjection(
  playerId: string,
  day?: number,
  horizonDays: number = 14,
): Promise<RiskProjectionResponse> {
  const extra = `horizon_days=${horizonDays}`;
  return fetchApi(`/forecast/player/${playerId}/risk${dayParam(day, extra)}`);
}

// ---------------------------------------------------------------------------
// 3. Forecast summary
// ---------------------------------------------------------------------------

export async function getForecastSummary(
  playerId: string,
  day?: number,
  horizonDays: number = 14,
): Promise<ForecastSummaryResponse> {
  const extra = `horizon_days=${horizonDays}`;
  return fetchApi(`/forecast/player/${playerId}/summary${dayParam(day, extra)}`);
}

// ---------------------------------------------------------------------------
// 4. Simulate a hypothetical action
// ---------------------------------------------------------------------------

export async function simulateAction(
  playerId: string,
  req: SimulationRequest,
  day?: number,
): Promise<SimulationResponse> {
  return fetchApi(`/forecast/player/${playerId}/simulate${dayParam(day)}`, { method: 'POST', body: JSON.stringify(req) });
}

// ---------------------------------------------------------------------------
// 5. Scenario comparison
// ---------------------------------------------------------------------------

export async function compareScenarios(
  playerId: string,
  req: ScenarioComparisonRequest,
  day?: number,
): Promise<ScenarioComparisonResponse> {
  return fetchApi(`/forecast/player/${playerId}/compare${dayParam(day)}`, { method: 'POST', body: JSON.stringify(req) });
}

// ---------------------------------------------------------------------------
// 6. Decision guidance
// ---------------------------------------------------------------------------

export async function getDecisionGuidance(
  playerId: string,
  day?: number,
  horizonDays: number = 14,
): Promise<DecisionGuidanceResponse> {
  const extra = `horizon_days=${horizonDays}`;
  return fetchApi(`/forecast/player/${playerId}/guidance${dayParam(day, extra)}`);
}

// ---------------------------------------------------------------------------
// 7. Build and persist forecast snapshot
// ---------------------------------------------------------------------------

export async function buildForecastSnapshot(
  playerId: string,
  day?: number,
  horizonDays: number = 14,
): Promise<ForecastSnapshotResponse> {
  const extra = `horizon_days=${horizonDays}`;
  return fetchApi(`/forecast/player/${playerId}/snapshot${dayParam(day, extra)}`, { method: 'POST', body: JSON.stringify({}) });
}

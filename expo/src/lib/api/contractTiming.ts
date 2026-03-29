// Step 41 — Contract Timing, Recurring Obligations, and Calendar Pressure API client

import { fetchApi } from '@/lib/apiClient';
import {
  CashTimingPressureStateResponse,
  ContractPressureSummaryResponse,
  DueSoonSummaryResponse,
  PlayerContractScheduleResponse,
  UpcomingObligationWindowResponse,
} from '@/types/contractTiming';


function dayParam(day?: number): string {
  return day !== undefined ? `?day=${day}` : '';
}

// ---------------------------------------------------------------------------
// Contract schedule (build + persist)
// ---------------------------------------------------------------------------

export async function getContractSchedule(
  playerId: string,
  day?: number,
): Promise<PlayerContractScheduleResponse> {
  return fetchApi(`/contracts/player/${playerId}/schedule${dayParam(day)}`);
}

// ---------------------------------------------------------------------------
// Upcoming obligation window
// ---------------------------------------------------------------------------

export async function getUpcomingObligationWindow(
  playerId: string,
  day?: number,
): Promise<UpcomingObligationWindowResponse> {
  return fetchApi(`/contracts/player/${playerId}/upcoming-window${dayParam(day)}`);
}

// ---------------------------------------------------------------------------
// Cash timing pressure state
// ---------------------------------------------------------------------------

export async function getCashTimingPressure(
  playerId: string,
  day?: number,
): Promise<CashTimingPressureStateResponse> {
  return fetchApi(`/contracts/player/${playerId}/cash-timing-pressure${dayParam(day)}`);
}

// ---------------------------------------------------------------------------
// Due-soon summary
// ---------------------------------------------------------------------------

export async function getDueSoonSummary(
  playerId: string,
  day?: number,
): Promise<DueSoonSummaryResponse> {
  return fetchApi(`/contracts/player/${playerId}/due-soon-summary${dayParam(day)}`);
}

// ---------------------------------------------------------------------------
// Full pressure summary
// ---------------------------------------------------------------------------

export async function getContractPressureSummary(
  playerId: string,
  day?: number,
): Promise<ContractPressureSummaryResponse> {
  return fetchApi(`/contracts/player/${playerId}/pressure-summary${dayParam(day)}`);
}

// ---------------------------------------------------------------------------
// Mutations (POST)
// ---------------------------------------------------------------------------

export async function generateContracts(
  playerId: string,
  day?: number,
): Promise<Record<string, unknown>> {
  return fetchApi(`/contracts/player/${playerId}/generate-contracts${dayParam(day)}`, { method: 'POST' });
}

export async function advanceContractEvents(
  playerId: string,
  day?: number,
): Promise<Record<string, unknown>> {
  return fetchApi(`/contracts/player/${playerId}/advance-events${dayParam(day)}`, { method: 'POST' });
}

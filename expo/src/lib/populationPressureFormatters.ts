import { RegionHeatSummaryResponse, RegionPopulationStateResponse } from '@/types/populationPressure';

export function formatHeatLabel(heatLevel?: string | null): string {
  const value = String(heatLevel || '').trim().toLowerCase();
  if (!value) return 'Unknown';
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function buildRegionStateSummary(state?: RegionPopulationStateResponse | null): string {
  if (!state) return 'Population pressure data unavailable.';
  const heat = formatHeatLabel(state.heat_level);
  const congestion = Number(state.congestion_score || 0).toFixed(0);
  const opportunity = Number(state.opportunity_density_score || 0).toFixed(0);
  return `${heat} region: opportunity ${opportunity}, congestion ${congestion}.`;
}

export function buildRegionHeatSummary(heat?: RegionHeatSummaryResponse | null): string {
  if (!heat) return 'Region heat unavailable.';
  return `${heat.dominant_upside} ${heat.dominant_friction}`;
}

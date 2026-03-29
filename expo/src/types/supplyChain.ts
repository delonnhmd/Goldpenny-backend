// Step 43: Supply Chain Graph + Bottleneck Opportunity Engine — TypeScript type definitions.
// Auto-generated from app/schemas/supply_chain.py

// ── Step 43: Physical Node Responses ───────────────────────────────────────

export interface SupplyChainNodeStateResponse {
  node_id: string;
  abstract_node: string;
  availability: number;
  region: string;
  region_modifier: number;
  region_adjusted_availability: number;
  reliability_scale: number;
  source: string;
}

export interface SupplyChainBottleneckResponse {
  node_id: string;
  availability: number;
  severity_label: string;
  affected_baskets: string[];
  affected_jobs: string[];
  reason_summary: string;
  rank: number;
}

export interface BasketSupplyMultiplierResponse {
  basket_type: string;
  supply_multiplier: number;
  cost_pressure_label: string;
  primary_bottleneck_node: string | null;
  short_summary: string;
}

export interface JobPressureResponse {
  job_key: string;
  job_pressure_multiplier: number;
  opportunity_label: string;
  source_bottleneck_nodes: string[];
  short_summary: string;
}

export interface SupplyChainSummaryResponse {
  day: number;
  top_bottleneck_node: string | null;
  top_bottleneck_severity: string;
  most_affected_basket: string | null;
  most_affected_basket_multiplier: number;
  best_job_opportunity: string | null;
  best_job_pressure_multiplier: number;
  overall_stress_score: number;
  short_summary: string;
  node_states: SupplyChainNodeStateResponse[];
  bottlenecks: SupplyChainBottleneckResponse[];
  basket_multipliers: BasketSupplyMultiplierResponse[];
  job_pressure: JobPressureResponse[];
}

export interface SupplyChainStoryResponse {
  day: number;
  shortage_story: string;
  bottleneck_highlights: string[];
  basket_impact_notes: string[];
  job_opportunity_hints: string[];
  practical_current_actions: string[];
}

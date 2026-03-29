// ─── PORTRAIT LAYOUT LOCK (Step 58) ───────────────────────────────────────────
// Gold Penny is a one-hand portrait-first mobile game.
// The permanent 3-layer screen hierarchy is:
//
//  LAYER 1 — Context (top, scroll, compact):
//    daily_brief        — headline + economy summary + top warning/opportunity
//
//  LAYER 2 — Player State (below context, scroll, compact):
//    player_stats       — cash, debt, net flow, key pressure indicators
//
//  LAYER 3 — Action Zone (bottom, always visible, thumb-friendly):
//    ThumbReachActionDock — Work | End Day (primary row)
//                         — Business | Recovery | Stocks | Jobs (secondary row)
//
// Primary scroll also includes contextual primary cards collapsed by default:
//    business_operations  — shown when player has active business (collapsible)
//    stock_market         — always available (collapsible)
//    action_hub           — full action list (expanded by default)
//    random_event         — shown when active event exists
//
// Everything else is SECONDARY (collapsible, below the scroll):
//    economy_overview, business_insights, planning_commitment (includes
//    strategic_recommendation), progression, world_memory
//
// Do not move canonical logic items here. Layout changes only.
// ────────────────────────────────────────────────────────────────────────────────

export type SecondaryGroupKey =
  | 'economy_overview'
  | 'business_insights'
  | 'planning_commitment'
  | 'progression'
  | 'world_memory';

export interface SecondaryGroupConfig {
  key: SecondaryGroupKey;
  title: string;
  sectionDependencies: string[];
  defaultCollapsed: boolean;
}

export const PRIMARY_SECTION_KEYS = [
  'daily_brief',
  'player_stats',
  'action_hub',
] as const;

export const SECONDARY_GROUP_CONFIGS: SecondaryGroupConfig[] = [
  {
    key: 'economy_overview',
    title: 'Economy + Market',
    sectionDependencies: [
      'market_overview',
      'price_trends',
      'commute_pressure',
      'housing_tradeoff',
      'economy_explainer',
      'future_teasers',
    ],
    defaultCollapsed: true,
  },
  {
    key: 'business_insights',
    title: 'Business + Margins',
    sectionDependencies: ['business_margins', 'business_plan'],
    defaultCollapsed: true,
  },
  {
    key: 'planning_commitment',
    title: 'Planning + Commitment',
    sectionDependencies: [
      'strategic_recommendation',
      'strategic_planning',
      'debt_growth',
      'recovery_vs_push',
      'commitment',
      'future_preparation',
    ],
    defaultCollapsed: true,
  },
  {
    key: 'progression',
    title: 'Progression',
    sectionDependencies: ['progression', 'weekly_summary', 'weekly_missions'],
    defaultCollapsed: true,
  },
  {
    key: 'world_memory',
    title: 'World Memory',
    sectionDependencies: ['world_memory'],
    defaultCollapsed: true,
  },
];

export const UI_LAYOUT_CONFIG = {
  primarySections: PRIMARY_SECTION_KEYS,
  secondaryGroups: SECONDARY_GROUP_CONFIGS,
  onboarding: {
    hideSecondaryDuringOnboarding: true,
    forceCollapseSecondary: true,
  },
  // strategic_recommendation is always rendered inside planning_commitment secondary group.
  // Keep player_state / risk_opportunity / quick_actions to guard against stale onboarding keys.
  hideByDefault: [
    'player_state',
    'risk_opportunity',
    'quick_actions',
    'strategic_recommendation',
  ],
};

import {
  ActionPreviewRequest,
  ActionPreviewResponse,
  DailyActionHubResponse,
  EndOfDaySummaryResponse,
  PlayerDashboardResponse,
} from '@/types/gameplay';
import { EconomyPresentationSummaryResponse } from '@/types/economyPresentation';
import { PlayerBusinessesResponse } from '@/types/business';
import { StockMarketSnapshotResponse } from '@/types/stocks';
import { BusinessPlanResponse } from '@/types/strategicPlanning';

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

export function createMockDashboard(playerId: string): PlayerDashboardResponse {
  const date = todayIsoDate();
  return {
    player_id: playerId,
    as_of_date: date,
    headline: 'Protect cash first, then take one clear growth move.',
    daily_brief:
      'Food and transport costs climbed, but your current job remains stable. A focused work shift keeps the day resilient.',
    stats: {
      cash_xgp: 1284.25,
      debt_xgp: 7420.5,
      net_worth_xgp: -1198.75,
      stress: 44,
      health: 72,
      credit_score: 638,
      current_job: 'Retail Clerk',
      region_key: 'outer_ring',
    },
    state_cards: [
      {
        title: 'Cash Position',
        summary: 'Cash can absorb one weak day but not two.',
      },
      {
        title: 'Debt Pressure',
        summary: 'Debt is still heavy versus liquid cash.',
      },
    ],
    top_opportunities: [
      {
        key: 'opp_work_shift',
        title: 'Stable Shift Available',
        description: 'A full shift keeps cashflow positive today.',
        severity: 'low',
        category: 'job_income',
      },
      {
        key: 'opp_food_truck',
        title: 'Lunch Demand Window',
        description: 'Food truck demand is elevated in downtown lanes.',
        severity: 'medium',
        category: 'business',
      },
    ],
    top_risks: [
      {
        key: 'risk_basket_transport',
        title: 'Transport Basket Rising',
        description: 'Fuel and commute costs can erode net cash quickly.',
        severity: 'high',
        category: 'basket',
      },
      {
        key: 'risk_debt_ratio',
        title: 'Debt-to-cash ratio remains elevated',
        description: 'Avoid overcommitting to high-volatility actions.',
        severity: 'medium',
        category: 'debt',
      },
    ],
    recommended_actions: [
      {
        action_key: 'work_shift',
        title: 'Work Shift',
        reason: 'Best immediate income-per-time outcome.',
      },
      {
        action_key: 'operate_business',
        title: 'Run Business',
        reason: 'Margins are positive if inventory is already stocked.',
      },
    ],
    debug_meta: {
      source: 'local_mock',
      daily_time_units: 10,
    },
  };
}

export function createMockActionHub(playerId: string): DailyActionHubResponse {
  return {
    player_id: playerId,
    as_of_date: todayIsoDate(),
    recommended_actions: [
      {
        action_key: 'work_shift',
        title: 'Work Main Shift',
        description: 'Run a standard shift for steady daily income.',
        status: 'recommended',
        blockers: [],
        tradeoffs: ['Consumes time units that could be used for business.'],
        warnings: [],
        confidence_level: 'high',
        parameters: { hours_worked: 8 },
      },
      {
        action_key: 'operate_business',
        title: 'Operate Food Truck',
        description: 'Convert stocked inventory into same-day cash.',
        status: 'recommended',
        blockers: [],
        tradeoffs: ['Higher variance versus fixed wage work.'],
        warnings: ['Margins weaken if transport input costs spike.'],
        confidence_level: 'medium',
        parameters: {},
      },
    ],
    available_actions: [
      {
        action_key: 'study',
        title: 'Skill Training',
        description: 'Invest time for better long-term income growth.',
        status: 'available',
        blockers: [],
        tradeoffs: ['No direct cash now.'],
        warnings: [],
        confidence_level: 'medium',
        parameters: { training_hours: 2 },
      },
      {
        action_key: 'rest',
        title: 'Recovery Block',
        description: 'Reduce stress and protect health before tomorrow.',
        status: 'available',
        blockers: [],
        tradeoffs: ['No immediate cash gain.'],
        warnings: [],
        confidence_level: 'high',
        parameters: {},
      },
      {
        action_key: 'side_income',
        title: 'Side Gig',
        description: 'Short ride-share block for variable earnings.',
        status: 'available',
        blockers: [],
        tradeoffs: ['Higher stress per unit than core job shifts.'],
        warnings: ['Income range is volatile.'],
        confidence_level: 'low',
        parameters: { hours_worked: 3 },
      },
    ],
    blocked_actions: [
      {
        action_key: 'change_region',
        title: 'Move Region',
        description: 'Switch housing region to adjust commute pressure.',
        status: 'blocked',
        blockers: ['Needs more savings buffer before relocation.'],
        blocker_text: 'Needs more savings buffer before relocation.',
        tradeoffs: [],
        warnings: [],
        confidence_level: 'unknown',
        parameters: {},
      },
    ],
    top_tradeoffs: [
      'Work first to stabilize cash, then take one optional upside move.',
      'Avoid stacking high-stress actions if health is below 70.',
    ],
    next_risk_warnings: [
      'Transport basket pressure may raise tomorrow expenses.',
      'Debt servicing cost is still above target safety threshold.',
    ],
    debug_meta: {
      source: 'local_mock',
    },
  };
}

export function createMockEconomySummary(playerId: string): EconomyPresentationSummaryResponse {
  const date = todayIsoDate();
  return {
    player_id: playerId,
    as_of_date: date,
    current_day: 4,
    market_overview: {
      player_id: playerId,
      as_of_date: date,
      current_market_mood: 'mixed',
      headline_drivers: ['Fuel up +1.9%', 'Fresh produce normalizing', 'Rent trend stable'],
      top_winners: ['Prepared meals', 'Local logistics'],
      top_losers: ['Commuter transport', 'Cold storage'],
      macro_trend_labels: {
        inflation: 'sticky',
        employment: 'stable',
      },
      basket_pressure_labels: {
        transport: 'high',
        essentials: 'moderate',
      },
      short_explainer: 'Costs are uneven: transport is hot while food baskets are less volatile.',
      debug_meta: { source: 'local_mock' },
    },
    price_trends: {
      player_id: playerId,
      as_of_date: date,
      items: [
        {
          basket_key: 'transport',
          current_level: 108.4,
          short_term_trend: 'rising',
          volatility_label: 'high',
          primary_driver: 'Fuel supply constraint',
          player_impact_summary: 'Commute-related actions cost more this day.',
        },
        {
          basket_key: 'produce',
          current_level: 101.2,
          short_term_trend: 'stable',
          volatility_label: 'moderate',
          primary_driver: 'Regional availability recovery',
          player_impact_summary: 'Food business margins are workable with disciplined inventory.',
        },
        {
          basket_key: 'essentials',
          current_level: 103.7,
          short_term_trend: 'rising',
          volatility_label: 'moderate',
          primary_driver: 'Distribution bottlenecks',
          player_impact_summary: 'Baseline household spend is trending higher.',
        },
      ],
      debug_meta: { source: 'local_mock' },
    },
    business_margins: {
      player_id: playerId,
      as_of_date: date,
      items: [
        {
          business_key: 'food_truck',
          margin_outlook: 'favorable',
          demand_outlook: 'supportive',
          cost_pressure: 'moderate',
          risk_factors: ['Transport basket volatility'],
          opportunity_factors: ['Strong lunch-hour demand'],
          short_explainer: 'Food truck margins are positive if inventory turns quickly.',
        },
        {
          business_key: 'fruit_shop',
          margin_outlook: 'mixed',
          demand_outlook: 'stable',
          cost_pressure: 'moderate',
          risk_factors: ['Cold chain energy costs'],
          opportunity_factors: ['Consistent neighborhood demand'],
          short_explainer: 'Fruit shop cashflow is stable but sensitive to spoilage and input timing.',
        },
      ],
      debug_meta: { source: 'local_mock' },
    },
    commute_pressure: {
      player_id: playerId,
      as_of_date: date,
      region_key: 'outer_ring',
      commute_pressure_level: 'moderate',
      estimated_commute_burden: 'Manageable but trending upward',
      stress_impact_label: '+2 to +4 stress if over-scheduled',
      time_impact_label: 'Medium travel overhead',
      housing_tradeoff_summary: 'Closer housing reduces commute stress but increases fixed costs.',
      suggested_current_responses: ['Bundle actions by area', 'Prioritize high-yield shifts'],
      future_locked_solutions: ['Region relocation unlock at higher cash buffer'],
      debug_meta: { source: 'local_mock' },
    },
    explainer: {
      player_id: playerId,
      as_of_date: date,
      why_costs_changed: 'Transport and essentials moved due to supply and fuel pressure.',
      why_business_changed: 'Demand remains solid in prepared food channels.',
      why_commute_changed: 'Outer ring travel costs rose with fuel prices.',
      why_stress_changed: 'Debt pressure plus longer travel windows increase stress risk.',
      this_week_focus: 'Preserve liquidity while taking stable income actions.',
      suggested_defensive_move: 'Work main shift before optional risk actions.',
      suggested_growth_move: 'Operate food truck once after cash baseline is secured.',
      debug_meta: { source: 'local_mock' },
    },
    future_teasers: {
      player_id: playerId,
      as_of_date: date,
      teasers: [
        {
          teaser_key: 'supply_contracts',
          title: 'Supplier Contract Route',
          body: 'Lock lower input costs once your reliability score improves.',
          unlock_status: 'locked',
          category: 'business',
        },
      ],
      debug_meta: { source: 'local_mock' },
    },
    daily_brief: {
      as_of_date: date,
      day: 4,
      headline: 'Stabilize first, then scale one action.',
      summary_lines: [
        'Transport costs remain the main pressure point.',
        'Job income is the safest way to defend cash today.',
      ],
      top_bottlenecks: ['Fuel availability'],
      top_basket_movers: ['transport +1.9%', 'essentials +0.8%'],
      top_job_changes: ['retail clerk stable', 'delivery variance high'],
      debug_meta: { source: 'local_mock' },
    },
    supply_chain_summary: {
      day: 4,
      top_bottleneck_node: 'fuel_distribution',
      top_bottleneck_severity: 'high',
      most_affected_basket: 'transport',
      most_affected_basket_multiplier: 1.09,
      best_job_opportunity: 'retail_clerk',
      best_job_pressure_multiplier: 1.03,
      overall_stress_score: 0.58,
      short_summary: 'Fuel distribution is the main cost pressure node.',
      node_states: [
        {
          node_id: 'fuel_distribution',
          abstract_node: 'fuel_distribution',
          availability: 0.72,
          region: 'metro',
          region_modifier: 1.04,
          region_adjusted_availability: 0.75,
          reliability_scale: 0.7,
          source: 'mock',
        },
      ],
      bottlenecks: [
        {
          node_id: 'fuel_distribution',
          availability: 0.72,
          severity_label: 'high',
          affected_baskets: ['transport'],
          affected_jobs: ['delivery_driver'],
          reason_summary: 'Fuel throughput below seasonal baseline.',
          rank: 1,
        },
      ],
      basket_multipliers: [
        {
          basket_type: 'transport',
          supply_multiplier: 1.09,
          cost_pressure_label: 'high',
          primary_bottleneck_node: 'fuel_distribution',
          short_summary: 'Transport basket remains elevated.',
        },
      ],
      job_pressure: [
        {
          job_key: 'retail_clerk',
          job_pressure_multiplier: 1.03,
          opportunity_label: 'stable',
          source_bottleneck_nodes: ['fuel_distribution'],
          short_summary: 'Retail demand remains resilient.',
        },
      ],
    },
    supply_chain_story: {
      day: 4,
      shortage_story: 'Fuel distribution slowed, lifting transport costs and commute pressure.',
      bottleneck_highlights: ['Fuel distribution constraint remains unresolved.'],
      basket_impact_notes: ['Transport basket up while produce holds steady.'],
      job_opportunity_hints: ['Steady retail shifts remain lower risk than delivery side gigs.'],
      practical_current_actions: ['Take a stable shift first', 'Delay high-travel plans'],
    },
    settlement_summary: {
      day_number: 3,
      income_xgp: 312.4,
      expenses_xgp: 276.3,
      net_change_xgp: 36.1,
      cash_after_xgp: 1284.25,
      stress_change: 2,
      health_change: -1,
      debug_meta: { source: 'local_mock' },
    },
    player_warnings: [
      'Transport costs are still elevated.',
      'Debt servicing risk remains above comfort band.',
    ],
    player_opportunities: [
      'Stable work shifts are still paying reliably.',
      'Food truck demand remains healthy in current region.',
    ],
    debug_meta: { source: 'local_mock' },
  };
}

export function createMockStockMarket(playerId: string): StockMarketSnapshotResponse {
  return {
    player_id: playerId,
    latest_day: 4,
    stocks: [
      {
        stock_id: 'GPTECH',
        stock_name: 'GP Tech',
        sector_key: 'technology',
        current_price: 42.6,
        previous_close: 40.5,
        daily_change_pct: 5.19,
        latest_day: 4,
        sector_signal_summary: 'Technology closed strong on demand momentum.',
        volatility_label: 'hot',
        can_trade: true,
        holdings_quantity: 3,
        holdings_cost_basis: 108.0,
        holdings_market_value: 127.8,
        holdings_unrealized_pnl: 19.8,
      },
      {
        stock_id: 'GPRETAIL',
        stock_name: 'GP Retail',
        sector_key: 'retail',
        current_price: 25.2,
        previous_close: 25.7,
        daily_change_pct: -1.95,
        latest_day: 4,
        sector_signal_summary: 'Retail cooled slightly after yesterday surge.',
        volatility_label: 'active',
        can_trade: true,
        holdings_quantity: 0,
        holdings_cost_basis: 0,
        holdings_market_value: 0,
        holdings_unrealized_pnl: 0,
      },
    ],
    portfolio: {
      available_cash_xgp: 1284.25,
      total_market_value_xgp: 127.8,
      total_cost_basis_xgp: 108.0,
      total_unrealized_pnl_xgp: 19.8,
      total_portfolio_value_xgp: 1412.05,
      holdings_count: 1,
    },
  };
}

export function createMockBusinesses(playerId: string): PlayerBusinessesResponse {
  return {
    player_id: playerId,
    businesses: [
      {
        business_id: 'biz_food_truck_01',
        player_id: playerId,
        business_type: 'food_truck',
        business_name: 'South Loop Truck',
        is_active: true,
        region_key: 'downtown',
        level: 'starter',
        reputation: 18,
        cash_invested_xgp: 1800,
        inventory_produce_units: 3,
        inventory_essentials_units: 5,
        inventory_protein_units: 2,
        operating_mode: 'balanced',
        last_operated_on: null,
      },
    ],
    profit_snapshot: {
      player_id: playerId,
      day: 4,
      total_businesses: 1,
      active_businesses: 1,
      latest_daily_profit_xgp: 86.2,
      trailing_7d_profit_xgp: 241.7,
      inventory_estimated_value_xgp: 312.0,
      business_estimated_value_xgp: 1820.0,
      business_type_breakdown: [
        {
          business_type: 'food_truck',
          count: 1,
          active_count: 1,
          inventory_value_xgp: 312.0,
          latest_daily_profit_xgp: 86.2,
        },
      ],
    },
  };
}

export function createMockBusinessPlan(playerId: string): BusinessPlanResponse {
  return {
    player_id: playerId,
    as_of_date: todayIsoDate(),
    items: [
      {
        business_key: 'food_truck',
        business_present: true,
        current_mode: 'balanced',
        demand_outlook: 'supportive',
        input_cost_outlook: 'moderate',
        margin_stability: 'stable',
        recommendation_over_horizon:
          'Operate once after securing base income, then keep inventory tight.',
        key_watch_item: 'Transport basket pressure can tighten daily margin quickly.',
      },
      {
        business_key: 'fruit_shop',
        business_present: false,
        current_mode: 'none',
        demand_outlook: 'stable',
        input_cost_outlook: 'moderate',
        margin_stability: 'mixed',
        recommendation_over_horizon: 'Delay expansion until debt pressure is reduced.',
        key_watch_item: 'Fixed-cost commitments can overwhelm thin cash buffers.',
      },
    ],
    debug_meta: { source: 'local_mock' },
  };
}

export function createMockEndOfDaySummary(playerId: string): EndOfDaySummaryResponse {
  return {
    player_id: playerId,
    as_of_date: todayIsoDate(),
    total_earned_xgp: 312.4,
    total_spent_xgp: 276.3,
    net_change_xgp: 36.1,
    guided_day_number: 0,
    guided_learning_title: null,
    guided_earned_summary: null,
    guided_spent_summary: null,
    guided_change_summary: null,
    guided_watch_tomorrow: null,
    biggest_gain: 'Consistent work shift income protected cashflow.',
    biggest_loss: 'Transport basket increase lifted total expenses.',
    stress_delta: 2,
    health_delta: -1,
    skill_delta: 1,
    credit_score_delta: 2,
    distress_state: 'watch',
    tomorrow_warnings: [
      'Watch transport basket movement before high-commute actions.',
      'Debt servicing remains the main drag on net worth.',
    ],
    debug_meta: {
      source: 'local_mock',
    },
  };
}

export function createMockActionPreview(
  playerId: string,
  payload: ActionPreviewRequest,
): ActionPreviewResponse {
  const actionKey = String(payload.action_key || 'work_shift');
  const label = actionKey.replace(/_/g, ' ');
  const isWork = actionKey.includes('work');
  const isBusiness = actionKey.includes('business');

  return {
    player_id: playerId,
    action_key: payload.action_key,
    summary: isBusiness
      ? 'Business operation can produce upside, but margin risk rises with transport pressure.'
      : isWork
        ? 'Work shift provides the most stable immediate cash gain.'
        : `Preview for ${label}.`,
    expected_cash_impact: {
      label: 'Cash',
      direction: 'up',
      amount: isBusiness ? 55 : 120,
      text: isBusiness ? '+55 xgp (variable)' : '+120 xgp (stable)',
    },
    expected_stress_impact: {
      label: 'Stress',
      direction: isBusiness ? 'up' : 'flat',
      amount: isBusiness ? 4 : 1,
      text: isBusiness ? '+4 (pressure)' : '+1',
    },
    expected_health_impact: {
      label: 'Health',
      direction: 'down',
      amount: -1,
      text: '-1',
    },
    expected_time_impact: {
      label: 'Time',
      direction: 'down',
      amount: -3,
      text: '-3 units',
    },
    expected_career_impact: {
      label: 'Career',
      direction: isWork ? 'up' : 'flat',
      amount: isWork ? 2 : 0,
      text: isWork ? 'small progression gain' : 'neutral',
    },
    expected_distress_impact: {
      label: 'Distress',
      direction: 'flat',
      amount: 0,
      text: 'neutral',
    },
    blockers: [],
    warnings: isBusiness
      ? ['Proceed only if cash remains above your safety threshold.']
      : [],
    confidence_level: isBusiness ? 'medium' : 'high',
    debug_meta: {
      source: 'local_mock',
    },
  };
}

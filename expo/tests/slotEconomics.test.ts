import test from 'node:test';
import assert from 'node:assert/strict';

import {
  calculateSlotCurrentValue,
  calculateSlotRevenuePreview,
  createSlotEconomicRecord,
  getSlotBottomSheetState,
  getSlotBusinessBadgeState,
  getStableSlotAddress,
  isHotSlot,
} from '../src/lib/slotEconomics.ts';
import { mergePortfolioSummaryWithSandbox } from '../src/lib/portfolioSummary.ts';

test('same slot_id returns same address', () => {
  const first = getStableSlotAddress({ slot_id: 'downtown_exchange:exchange_lot_01', district: 'Downtown', region: 'downtown' });
  const second = getStableSlotAddress({ slot_id: 'downtown_exchange:exchange_lot_01', district: 'Downtown', region: 'downtown' });

  assert.equal(first, second);
});

test('downtown slots have higher traffic than suburban on average', () => {
  const downtown = [
    createSlotEconomicRecord({ slot_id: 'd-1', district: 'Downtown', region: 'downtown', slot_type: 'commercial_core', purchase_price: 420, traffic_score: 82, development_potential: 86 }),
    createSlotEconomicRecord({ slot_id: 'd-2', district: 'Downtown', region: 'downtown', slot_type: 'mixed_use', purchase_price: 390, traffic_score: 76, development_potential: 84 }),
  ];
  const suburban = [
    createSlotEconomicRecord({ slot_id: 's-1', district: 'Suburban', region: 'suburban', slot_type: 'residential_edge', purchase_price: 210, traffic_score: 36, development_potential: 62 }),
    createSlotEconomicRecord({ slot_id: 's-2', district: 'Suburban', region: 'suburban', slot_type: 'mixed_use', purchase_price: 255, traffic_score: 44, development_potential: 70 }),
  ];

  const avg = (rows) => rows.reduce((sum, row) => sum + row.foot_traffic_score, 0) / rows.length;
  assert.ok(avg(downtown) > avg(suburban));
});

test('suburban slots have lower risk than downtown on average', () => {
  const downtown = createSlotEconomicRecord({
    slot_id: 'risk-downtown',
    district: 'Downtown',
    region: 'downtown',
    slot_type: 'commercial_core',
    purchase_price: 450,
    traffic_score: 88,
    development_potential: 90,
  });
  const suburban = createSlotEconomicRecord({
    slot_id: 'risk-suburban',
    district: 'Suburban',
    region: 'suburban',
    slot_type: 'residential_edge',
    purchase_price: 220,
    traffic_score: 42,
    development_potential: 68,
  });

  assert.ok(suburban.risk_score < downtown.risk_score);
});

test('current value is clamped correctly', () => {
  assert.equal(calculateSlotCurrentValue({
    purchase_price: 1000,
    demand_score: 200,
    foot_traffic_score: 200,
    risk_score: 0,
    district_category: 'downtown',
  }), 1750);

  assert.equal(calculateSlotCurrentValue({
    purchase_price: 1000,
    demand_score: -100,
    foot_traffic_score: -100,
    risk_score: 200,
    district_category: 'suburban',
  }), 750);
});

test('expected revenue range increases with demand and traffic', () => {
  const low = calculateSlotRevenuePreview({
    slot_id: 'rev-low',
    district: 'Suburban',
    region: 'suburban',
    slot_type: 'residential_edge',
    purchase_price: 220,
    demand_score: 48,
    foot_traffic_score: 44,
    competition_score: 36,
    risk_score: 24,
    supply_access_score: 72,
  }, 'fruit_shop');
  const high = calculateSlotRevenuePreview({
    slot_id: 'rev-high',
    district: 'Downtown',
    region: 'downtown',
    slot_type: 'commercial_core',
    purchase_price: 420,
    demand_score: 88,
    foot_traffic_score: 90,
    competition_score: 68,
    risk_score: 40,
    supply_access_score: 78,
  }, 'fruit_shop');

  assert.ok(high.expected_revenue > low.expected_revenue);
  assert.ok(high.high_revenue > low.high_revenue);
});

test('expected revenue range decreases with competition and risk', () => {
  const safer = calculateSlotRevenuePreview({
    slot_id: 'safe',
    district: 'Market',
    region: 'market',
    slot_type: 'mixed_use',
    purchase_price: 320,
    demand_score: 78,
    foot_traffic_score: 80,
    competition_score: 44,
    risk_score: 20,
    supply_access_score: 82,
  }, 'food_truck');
  const harsher = calculateSlotRevenuePreview({
    slot_id: 'harsh',
    district: 'Market',
    region: 'market',
    slot_type: 'mixed_use',
    purchase_price: 320,
    demand_score: 78,
    foot_traffic_score: 80,
    competition_score: 88,
    risk_score: 74,
    supply_access_score: 82,
  }, 'food_truck');

  assert.ok(harsher.expected_revenue < safer.expected_revenue);
});

test('owned slot value appears in portfolio without duplication', () => {
  const summary = {
    player_id: 'player-1',
    day: 14,
    cash: 1200,
    debt: 500,
    stock_holdings_value: 300,
    land_value: 0,
    business_value: 1800,
    inventory_value: 420,
    total_assets: 3720,
    net_worth: 3220,
    total_assets_without_sandbox_land: 3720,
    net_worth_without_sandbox_land: 3220,
    latest_business_profit: 45,
    trailing_7d_business_profit: 210,
    active_business_count: 1,
    owned_land: [],
    businesses: [
      {
        business_id: 'biz-1',
        business_type: 'food_truck',
        region: 'downtown',
        linked_slot_id: null,
        address: null,
        reputation: 24,
        inventory_value: 420,
        avg_7_day_profit: 38,
        estimated_business_value: 1480,
        last_net_profit: 52,
        last_operated_day: 14,
      },
    ],
  };

  const merged = mergePortfolioSummaryWithSandbox(summary, [
    {
      tile_key: 'downtown_exchange:exchange_lot_01',
      district_key: 'downtown_exchange',
      district_label: 'Downtown',
      region: 'downtown',
      zone_type: 'commercial_core',
      purchase_price_xgp: 800,
      traffic_score: 82,
      demand_score: 78,
      competition_score: 70,
      risk_score: 38,
      supply_access_score: 74,
      linked_business_id: 'biz-1',
      development_stage: 'built',
    },
  ]);

  assert.equal(merged.owned_land.length, 1);
  assert.ok(merged.land_value > 0);
  assert.equal(merged.businesses[0].linked_slot_id, 'downtown_exchange:exchange_lot_01');
});

test('linked business slot shows business badge and status', () => {
  const badge = getSlotBusinessBadgeState({
    linked_business_id: 'biz-1',
    linked_business_type: 'food_truck',
    owner_player_id: 'player-1',
  });

  assert.equal(badge.show_badge, true);
  assert.equal(badge.tone, 'built');
  assert.equal(badge.label, 'Food Truck');
});

test('hot slot visual flag appears for high demand and traffic', () => {
  assert.equal(isHotSlot({
    slot_id: 'hot-1',
    district: 'Downtown',
    region: 'downtown',
    purchase_price: 440,
    demand_score: 84,
    foot_traffic_score: 88,
    competition_score: 66,
    risk_score: 34,
    supply_access_score: 76,
  }), true);
});

test('slot bottom sheet renders correct buttons by state', () => {
  const unowned = getSlotBottomSheetState({ is_owned: false, has_linked_business: false });
  const owned = getSlotBottomSheetState({ is_owned: true, has_linked_business: false });
  const built = getSlotBottomSheetState({ is_owned: true, has_linked_business: true });

  assert.deepEqual(unowned.buttons.map((button) => button.key), ['buy_slot', 'inspect']);
  assert.deepEqual(owned.buttons.map((button) => button.key), ['open_business', 'inspect']);
  assert.deepEqual(built.buttons.map((button) => button.key), ['manage_operate_business', 'inspect']);
});

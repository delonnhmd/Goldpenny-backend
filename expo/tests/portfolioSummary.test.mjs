import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildDeterministicPortfolioAddress,
  mergePortfolioSummaryWithSandbox,
} from '../src/lib/portfolioSummary.ts';
import { calculateSlotCurrentValue } from '../src/lib/slotEconomics.ts';

test('portfolio slot address is deterministic', () => {
  const first = buildDeterministicPortfolioAddress('downtown:4:2', 'downtown');
  const second = buildDeterministicPortfolioAddress('downtown:4:2', 'downtown');

  assert.equal(first, second);
  assert.ok([
    '1203 Market Line Ave',
    '88 Riverfront Plaza',
    '410 Central Trade St',
    '726 Commerce Row',
    '51 Skyline Market Blvd',
  ].includes(first));
});

test('land current value formula clamps both high and low ends', () => {
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

test('frontend portfolio merge does not duplicate land value for the same slot', () => {
  const summary = {
    player_id: 'player-1',
    day: 14,
    cash: 1200,
    debt: 500,
    stock_holdings_value: 300,
    land_value: 900,
    business_value: 1800,
    inventory_value: 420,
    total_assets: 4620,
    net_worth: 4120,
    total_assets_without_sandbox_land: 3720,
    net_worth_without_sandbox_land: 3220,
    latest_business_profit: 45,
    trailing_7d_business_profit: 210,
    active_business_count: 1,
    owned_land: [
      {
        slot_id: 'slot-a',
        address: '1203 Market Line Ave',
        region: 'downtown',
        district: 'downtown',
        slot_type: 'commercial_core',
        purchase_price: 800,
        current_value: 900,
        demand_score: 66,
        linked_business_id: 'biz-1',
        linked_business_type: 'fruit_shop',
        ownership_status: 'owned_built',
      },
    ],
    businesses: [
      {
        business_id: 'biz-1',
        business_type: 'fruit_shop',
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

  const sandboxLots = [
    {
      tile_key: 'slot-a',
      district_key: 'downtown',
      district_label: 'Downtown',
      region: 'downtown',
      zone_type: 'commercial_core',
      purchase_price_xgp: 800,
      demand_score: 66,
      linked_business_id: 'biz-1',
      development_stage: 'built',
    },
  ];

  const merged = mergePortfolioSummaryWithSandbox(summary, sandboxLots);

  assert.equal(merged.owned_land.length, 1);
  assert.equal(merged.land_value, merged.owned_land[0].current_value);
  assert.equal(merged.total_assets, merged.total_assets_without_sandbox_land + merged.land_value);
  assert.equal(merged.businesses[0].address, '1203 Market Line Ave');
  assert.equal(merged.businesses[0].linked_slot_id, 'slot-a');
});

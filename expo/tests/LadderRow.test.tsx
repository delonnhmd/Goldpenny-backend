import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import TestRenderer, { act } from 'react-test-renderer';

import LadderRow, { LadderRoute } from '../src/components/gameMap/LadderRow';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function collectText(node: unknown): string[] {
  if (typeof node === 'string') return [node];
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(collectText);
  const children = (node as { children?: unknown[] }).children || [];
  return children.flatMap(collectText);
}

function renderRow(onNavigate: (route: LadderRoute) => void) {
  let renderer: TestRenderer.ReactTestRenderer | null = null;
  act(() => {
    renderer = TestRenderer.create(
      <LadderRow
        career={{ rankLabel: 'Junior Analyst', progressPct: 60, nextRankLabel: 'Senior' }}
        business={{ label: 'Food Truck', extraCount: 2, hasBusiness: true }}
        netWorth={{ available: true, deltaPct: 4.2, direction: 'up' }}
        onNavigate={onNavigate}
      />,
    );
  });
  if (!renderer) throw new Error('renderer missing');
  return renderer;
}

test('LadderRow renders career, business, and weekly net-worth ladder text', () => {
  const renderer = renderRow(() => undefined);
  const text = collectText(renderer.toJSON()).join(' ');

  assert.match(text, /Rank:\s+Junior Analyst\s+—\s+60\s*%\s+to\s+Senior/);
  assert.match(text, /Food Truck\s+\+2 more/);
  assert.match(text, /▲\s+4\.2% this week/);
});

test('LadderRow routes each pill to its expected gameplay screen', () => {
  const routes: LadderRoute[] = [];
  const renderer = renderRow((route) => {
    routes.push(route);
  });

  act(() => {
    renderer.root.findByProps({ testID: 'ladder-career' }).props.onPress();
    renderer.root.findByProps({ testID: 'ladder-business' }).props.onPress();
    renderer.root.findByProps({ testID: 'ladder-net-worth' }).props.onPress();
  });

  assert.deepEqual(routes, ['work', 'business', 'portfolio']);
});

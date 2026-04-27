import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import TestRenderer, { act } from 'react-test-renderer';

import StreakBadge from '../src/components/gameplay/StreakBadge';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function collectText(node: unknown): string[] {
  if (typeof node === 'string') return [node];
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(collectText);
  const children = (node as { children?: unknown[] }).children || [];
  return children.flatMap(collectText);
}

function renderText(element: React.ReactElement): string {
  let renderer: TestRenderer.ReactTestRenderer | null = null;
  act(() => {
    renderer = TestRenderer.create(element);
  });
  return collectText(renderer?.toJSON()).join(' ');
}

test('StreakBadge renders current and longest streak counts', () => {
  const text = renderText(<StreakBadge currentStreak={7} longestStreak={12} />);

  assert.match(text, /\u{1F525}/u);
  assert.match(text, /\b7\b/);
  assert.match(text, /longest\s+12/);
});

test('StreakBadge gracefully renders zero without longest subtitle', () => {
  const text = renderText(<StreakBadge currentStreak={0} longestStreak={0} />);

  assert.match(text, /\b0\b/);
  assert.doesNotMatch(text, /longest/);
});

import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import TestRenderer, { act } from 'react-test-renderer';

import ActionsRemainingIndicator from '../src/components/gameMap/ActionsRemainingIndicator';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as { requestAnimationFrame?: (callback: FrameRequestCallback) => number }).requestAnimationFrame = (callback) => {
  const id = setTimeout(() => callback(Date.now()), 0);
  return Number(id);
};
(globalThis as { cancelAnimationFrame?: (id: number) => void }).cancelAnimationFrame = (id) => {
  clearTimeout(id);
};

function collectText(node: unknown): string[] {
  if (typeof node === 'string') return [node];
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(collectText);
  const children = (node as { children?: unknown[] }).children || [];
  return children.flatMap(collectText);
}

function renderText(element: React.ReactElement): { text: string; unmount: () => void } {
  let renderer: TestRenderer.ReactTestRenderer | null = null;
  act(() => {
    renderer = TestRenderer.create(element);
  });
  return {
    text: collectText(renderer?.toJSON()).join(' '),
    unmount: () => {
      act(() => {
        renderer?.unmount();
      });
    },
  };
}

test('ActionsRemainingIndicator renders remaining moves text', () => {
  const result = renderText(<ActionsRemainingIndicator actionsRemainingToday={3} />);
  assert.match(result.text, /3 moves left/);
  result.unmount();
});

test('ActionsRemainingIndicator renders ready-to-settle text', () => {
  const result = renderText(<ActionsRemainingIndicator actionsRemainingToday={0} />);
  assert.match(result.text, /Ready to settle/);
  result.unmount();
});

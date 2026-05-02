import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer, { act } from 'react-test-renderer';

import AnnualRecapCard, { buildAnnualRecapDisplayRows } from '../src/components/gameplay/AnnualRecapCard.tsx';

test('frontend renders recap card with fallback values', () => {
  const rows = buildAnnualRecapDisplayRows({ year: 1, title: 'Survivor' });
  assert.equal(rows.find((row) => row.key === 'days_survived')?.value, '0');
  assert.equal(rows.find((row) => row.key === 'credit_score')?.value, '650');

  let renderer: TestRenderer.ReactTestRenderer | null = null;
  act(() => {
    renderer = TestRenderer.create(
      <AnnualRecapCard recap={{ year: 1, title: 'Survivor' }} />,
    );
  });

  const tree = JSON.stringify(renderer?.toJSON());
  assert.match(tree, /Survivor/);
  assert.match(tree, /No major win recorded yet/);
  assert.match(tree, /No major loss recorded yet/);
  assert.match(tree, /No major event recorded yet/);
});

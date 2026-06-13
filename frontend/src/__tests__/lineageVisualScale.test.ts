import { describe, expect, it } from 'vitest';
import { fitZoom } from '../components/LineageCanvas';
import { getComfortNodeBox } from '../nodeVisualTokens';

describe('lineage visual scale', () => {
  it('uses the subquery node box for column-level graph node types', () => {
    const subqueryBox = getComfortNodeBox('subquery');

    for (const type of ['table', 'column', 'output', 'output_field']) {
      expect(getComfortNodeBox(type)).toEqual(subqueryBox);
    }
  });

  it('uses the same compact node box for other lineage node types as well', () => {
    const subqueryBox = getComfortNodeBox('subquery');

    for (const type of ['cte', 'expression', 'unknown']) {
      expect(getComfortNodeBox(type)).toEqual(subqueryBox);
    }
  });

  it('does not upscale small lineage graphs by default', () => {
    expect(fitZoom({ width: 360, height: 220 }, { width: 1200, height: 800 })).toBe(1);
  });
});

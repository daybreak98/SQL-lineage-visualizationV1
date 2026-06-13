import { describe, expect, it } from 'vitest';
import { fitZoom, LINEAGE_ZOOM_BASELINE, zoomDisplayPercent } from '../components/LineageCanvas';
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

  it('treats the former 72% subquery scale as the shared 100% visual baseline', () => {
    expect(LINEAGE_ZOOM_BASELINE).toBe(0.72);
    expect(fitZoom({ width: 360, height: 220 }, { width: 1200, height: 800 })).toBe(LINEAGE_ZOOM_BASELINE);
    expect(zoomDisplayPercent(LINEAGE_ZOOM_BASELINE)).toBe(100);
  });
});

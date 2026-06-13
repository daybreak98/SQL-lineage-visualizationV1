import { describe, expect, it } from 'vitest';
import { fitZoom, LINEAGE_ZOOM_BASELINE, zoomDisplayPercent } from '../components/LineageCanvas';
import { getComfortNodeBox } from '../nodeVisualTokens';

describe('lineage visual scale', () => {
  it('uses requested width ratios and a compact shared node height', () => {
    expect(getComfortNodeBox('table')).toMatchObject({ width: 207, height: 45 });
    expect(getComfortNodeBox('subquery')).toMatchObject({ width: 110, height: 45 });
    expect(getComfortNodeBox('cte')).toMatchObject({ width: 110, height: 45 });
  });

  it('keeps the remaining node types at the baseline width with the compact height', () => {
    for (const type of ['column', 'output', 'output_field', 'expression', 'unknown']) {
      expect(getComfortNodeBox(type)).toMatchObject({ width: 138, height: 45 });
    }
  });

  it('treats the former 72% subquery scale as the shared 100% visual baseline', () => {
    expect(LINEAGE_ZOOM_BASELINE).toBe(0.72);
    expect(fitZoom({ width: 360, height: 220 }, { width: 1200, height: 800 })).toBe(LINEAGE_ZOOM_BASELINE);
    expect(fitZoom({ width: 1600, height: 400 }, { width: 1100, height: 560 })).toBe(LINEAGE_ZOOM_BASELINE);
    expect(zoomDisplayPercent(LINEAGE_ZOOM_BASELINE)).toBe(100);
  });
});

import { describe, expect, it } from 'vitest';
import { findMetricForNode } from '../DetailPanel.c09';

const semanticsReport = {
  metrics: [
    {
      name: 'gmv',
      entity_id: 'output_column:gmv',
      expression: 'SUM(order_amount)',
      depends_on: ['dwd_order_di.order_amount'],
      aggregate_functions: ['SUM'],
      operators: [],
    },
  ],
};

describe('DetailPanel C09 metric lookup', () => {
  it('finds metric by output node id', () => {
    const metric = findMetricForNode({ id: 'output_column:gmv', type: 'output_field', label: 'gmv' }, semanticsReport);
    expect(metric?.name).toBe('gmv');
    expect(metric?.depends_on).toContain('dwd_order_di.order_amount');
  });

  it('finds metric by expression node id', () => {
    const metric = findMetricForNode({ id: 'expression:gmv', type: 'expression', label: 'gmv expression' }, semanticsReport);
    expect(metric?.name).toBe('gmv');
  });
});

export type GraphNodeType =
  | 'table'
  | 'column'
  | 'cte'
  | 'subquery'
  | 'expression'
  | 'output'
  | 'output_field'
  | 'unknown';

export const COMFORT_CANVAS = {
  minWidth: 1420,
  minHeight: 680,
  marginX: 90,
  marginY: 64,
  minRankGap: 210,
  minNodeGap: 86,
};

export const COMFORT_NODE_BOX: Record<string, { width: number; height: number; radius: number }> = {
  table: { width: 220, height: 55, radius: 18 },
  column: { width: 230, height: 52, radius: 16 },
  cte: { width: 138, height: 56, radius: 14 },
  subquery: { width: 138, height: 56, radius: 14 },
  expression: { width: 245, height: 55, radius: 16 },
  output: { width: 230, height: 58, radius: 20 },
  output_field: { width: 238, height: 52, radius: 16 },
  unknown: { width: 220, height: 52, radius: 16 },
};

export const COMFORT_EDGE = {
  strokeWidth: 1.7,
  activeStrokeWidth: 2.8,
  opacity: 0.72,
  dimOpacity: 0.12,
  activeOpacity: 1,
};

export function getComfortNodeBox(type: string) {
  return COMFORT_NODE_BOX[type] ?? COMFORT_NODE_BOX.unknown;
}

export function nodeBoxComfort(type: string): { width: number; height: number } {
  const box = getComfortNodeBox(type);
  return { width: box.width, height: box.height };
}

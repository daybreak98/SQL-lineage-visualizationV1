import type React from 'react';
import type { GraphColumnRow } from '../../types/lineage';
import { cx } from '../../utils/cx';

interface ColumnRowProps {
  column: GraphColumnRow;
  selected: boolean;
  lineageActive?: 'selected' | 'upstream' | 'downstream';
  dimmed?: boolean;
  onSelect: (entityId: string) => void;
  onDoubleClick: (entityId: string) => void;
}

export function ColumnRow({ column, selected, lineageActive, dimmed, onSelect, onDoubleClick }: ColumnRowProps) {
  const handleMouseDown = (event: React.MouseEvent) => {
    event.stopPropagation();
  };

  return (
    <button
      type="button"
      className={cx('column-row', dimmed && 'dimmed')}
      data-selected={selected || undefined}
      data-lineage-active={lineageActive}
      data-role={column.role}
      data-entity-id={column.entityId}
      onMouseDown={handleMouseDown}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(column.entityId);
      }}
      onDoubleClick={(event) => {
        event.stopPropagation();
        onDoubleClick(column.entityId);
      }}
      title={column.label}
    >
      <span className="column-row__target-port" />
      <span className="column-row__label">{column.label}</span>
      <span className="column-row__source-port" />
    </button>
  );
}

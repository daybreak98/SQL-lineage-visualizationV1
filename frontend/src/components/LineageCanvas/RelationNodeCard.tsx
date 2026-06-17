import type React from 'react';
import type { GraphNode } from '../../types/lineage';
import { cx } from '../../utils/cx';
import { ColumnRow } from './ColumnRow';

interface RelationNodeCardProps {
  node: GraphNode;
  box: { width: number; height: number };
  selectedEntityId: string;
  currentEntityIds: Set<string>;
  activeColumnEntityIds: Set<string>;
  dimmed: boolean;
  warning: boolean;
  dragging: boolean;
  downstreamImpact?: boolean;
  stale?: boolean;
  viewHighlighted?: boolean;
  onSelectRelation: (entityId: string) => void;
  onSelectColumn: (entityId: string) => void;
  onDoubleClickEntity: (entityId: string) => void;
  onToggleCollapsed: (entityId: string) => void;
  onStartDrag: (event: React.MouseEvent, node: GraphNode) => void;
}

export function RelationNodeCard({
  node,
  box,
  selectedEntityId,
  currentEntityIds,
  activeColumnEntityIds,
  dimmed,
  warning,
  dragging,
  downstreamImpact,
  stale,
  viewHighlighted,
  onSelectRelation,
  onSelectColumn,
  onDoubleClickEntity,
  onToggleCollapsed,
  onStartDrag,
}: RelationNodeCardProps) {
  const relationSelected = selectedEntityId === node.entityId;
  const columnSelected = node.columns?.some((column) => column.entityId === selectedEntityId) ?? false;

  return (
    <div
      className="relation-node"
      style={{ width: box.width, height: box.height }}
      data-type={node.type}
      data-selected={relationSelected || undefined}
      data-column-selected={columnSelected || undefined}
      data-relation-selected={relationSelected || undefined}
      data-current={currentEntityIds.has(node.entityId) || undefined}
      data-collapsed={node.collapsed || undefined}
      data-downstream-impact={downstreamImpact || undefined}
      data-warning={warning || undefined}
      data-stale={stale || undefined}
      data-dimmed={dimmed || undefined}
      data-dragging={dragging || undefined}
      data-view-highlight={viewHighlighted || undefined}
      data-full-label={node.label}
      onMouseDown={(event) => onStartDrag(event, node)}
      onClick={(event) => {
        event.stopPropagation();
        onSelectRelation(node.entityId);
      }}
      onDoubleClick={(event) => {
        event.stopPropagation();
        onDoubleClickEntity(node.entityId);
      }}
    >
      <div className="relation-node__header">
        <button
          type="button"
          className="relation-node__collapse"
          aria-label={node.collapsed ? 'Expand relation columns' : 'Collapse relation columns'}
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            onToggleCollapsed(node.entityId);
          }}
        >
          {node.collapsed ? '+' : '-'}
        </button>
        <div className="relation-node__identity">
          <span className="relation-node__kind">{node.tag ?? node.type.toUpperCase()}</span>
          <span className="relation-node__title">{node.label}</span>
        </div>
        <span className={cx('state-dot', warning && 'warn')} />
      </div>

      {!node.collapsed && (
        <div className="relation-node__columns">
          {(node.columns ?? []).map((column) => (
            <ColumnRow
              key={column.entityId}
              column={column}
              selected={selectedEntityId === column.entityId}
              dimmed={dimmed || Boolean(selectedEntityId && selectedEntityId !== 'out:group' && selectedEntityId !== column.entityId && !activeColumnEntityIds.has(column.entityId))}
              onSelect={onSelectColumn}
              onDoubleClick={onDoubleClickEntity}
            />
          ))}
        </div>
      )}

      {!node.collapsed && Boolean(node.hiddenColumnCount) && (
        <div className="relation-node__hidden">+{node.hiddenColumnCount} hidden</div>
      )}
    </div>
  );
}

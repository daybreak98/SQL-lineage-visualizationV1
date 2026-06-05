import type React from 'react';
import { buildPathContext, diagnosticsForEntity, entityName, entityOf } from '../data/selectors';
import type { DetailTab, Diagnostic, GraphEdge, WorkbenchState } from '../types/lineage';
import { cx } from '../utils/cx';

interface Props {
  state: WorkbenchState;
  setState: React.Dispatch<React.SetStateAction<WorkbenchState>>;
  onLocateSql?: (entityId: string) => void;
}

interface MappingViewItem {
  id: string;
  source: string;
  target: string;
  relation: string;
  confidence: 'high' | 'medium' | 'low';
}

function K({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="kv"><div className="kv-label">{label}</div><div className="kv-value">{value}</div></div>;
}

function DiagnosticCard({ diagnostic }: { diagnostic: Diagnostic }) {
  return <div className={cx('card diag', diagnostic.severity)}><div className="card-title">{diagnostic.code}</div><b>Reason:</b> {diagnostic.reason}<br /><b>Impact:</b> {diagnostic.impact}<br /><b>Action:</b> {diagnostic.action}</div>;
}

function relationFromEdgeType(type: GraphEdge['type']) {
  if (type === 'expr') return 'expression';
  if (type === 'join') return 'join_dependency';
  return 'direct';
}

function buildMappingViewItems(state: WorkbenchState): MappingViewItem[] {
  const edges = state.backendGraph?.edges ?? [];
  const relevantEdges = state.selectedMapping
    ? edges.filter((edge) => edge.mapping === state.selectedMapping)
    : edges.filter((edge) => edge.source === state.selectedEntity || edge.target === state.selectedEntity);

  const items = new Map<string, MappingViewItem>();

  for (const edge of relevantEdges) {
    const id = edge.mapping || edge.id;
    items.set(id, {
      id,
      source: edge.source,
      target: edge.target,
      relation: relationFromEdgeType(edge.type),
      confidence: edge.synthetic ? 'medium' : 'high',
    });
  }

  return Array.from(items.values());
}

function MappingList({ items, displayEntityName }: { items: MappingViewItem[]; displayEntityName: (entityId: string) => string }) {
  if (!items.length) return <div className="card">No backend edge mapping data for the current selection.</div>;

  return <div className="cards">{items.map((item) => <div key={item.id} className="card"><div className="card-title">{item.id}</div><K label="source -> target" value={`${displayEntityName(item.source)} -> ${displayEntityName(item.target)}`} /><K label="relation" value={item.relation} /><K label="confidence" value={item.confidence} /></div>)}</div>;
}

export function DetailPanel({ state, setState, onLocateSql }: Props) {
  const backendNodes = state.backendGraph?.nodes ?? [];
  const labelByEntityId = new Map(backendNodes.map((node) => [node.entityId, node.label]));
  const selectedBackendNode = backendNodes.find((node) => node.entityId === state.selectedEntity);
  const baseEntity = entityOf(state.selectedEntity);
  const entity = {
    id: state.selectedEntity,
    type: selectedBackendNode?.type ?? baseEntity?.type ?? 'unknown',
    name: selectedBackendNode?.label ?? baseEntity?.name ?? state.selectedEntity,
    comment: baseEntity?.comment ?? 'No backend entity metadata available.',
  };
  const relatedMappings = buildMappingViewItems(state);
  const loc = state.sourceLocations?.[state.selectedEntity];
  const pc = buildPathContext(state);
  const displayEntityName = (entityId: string) => labelByEntityId.get(entityId) ?? entityName(entityId);

  let body: React.ReactNode;
  if (state.detailMode !== 'expanded') {
    const first = relatedMappings[0];
    const line1 = first ? `${displayEntityName(first.source)} -> ${displayEntityName(first.target)} · ${first.relation} · ${first.confidence}` : `${entity.name} · ${entity.type} · ${state.selectedOutput ? pc.confidence : 'structure'}`;
    const line2 = first ? `source: ${displayEntityName(first.source)} -> target: ${displayEntityName(first.target)} · ${first.relation}` : `Upstream structure · ${diagnosticsForEntity(state, state.selectedEntity).length} diagnostics`;
    body = <div className="compact-lines"><K label="Selected" value={line1} /><K label="Mapping" value={line2} /><K label="SQL" value={loc ? `line ${loc.line} · ${loc.rangeType}` : 'location unavailable'} /></div>;
  } else if (state.detailTab === 'summary') {
    body = <div className="grid"><K label="entity" value={state.selectedEntity} /><K label="name" value={entity.name} /><K label="comment" value={entity.comment} /></div>;
  } else if (state.detailTab === 'mapping') {
    body = <MappingList items={relatedMappings} displayEntityName={displayEntityName} />;
  } else if (state.detailTab === 'source') {
    body = <div className="grid"><K label="location" value={loc ? `line ${loc.line}, col ${loc.col}` : 'unavailable'} /><K label="range_type" value={loc?.rangeType || 'unavailable'} /><K label="guard" value={state.trustStatus === 'trusted' ? 'exact if range exact' : 'blocked by stale/untrusted'} /></div>;
  } else if (state.detailTab === 'diagnostics') {
    const diagnostics = diagnosticsForEntity(state, state.selectedEntity);
    body = <div className="cards">{diagnostics.length ? diagnostics.map((diagnostic) => <DiagnosticCard key={diagnostic.id} diagnostic={diagnostic} />) : <div className="card"><div className="card-title">Diagnostics</div>No backend diagnostics for the current entity.</div>}</div>;
  } else {
    body = <div className="grid"><K label="result_grain" value="unavailable" /><K label="filters" value="unavailable" /><K label="semantic_layer" value="Semantics panel is not backed by current analysis data." /></div>;
  }

  const setTab = (tab: DetailTab) => setState((s) => ({ ...s, detailTab: tab }));

  return (
    <div className={cx('detail', state.detailMode === 'collapsed' && 'collapsed', state.detailMode === 'expanded' && 'expanded')}>
      <div className="detail-head">
        <div className="detail-title"><span className="rail" /><span className="detail-name">{relatedMappings[0]?.id ?? entity.name}</span><span className="badge">{relatedMappings.length ? 'edge_mapping' : entity.type}</span><span className="badge">{state.trustStatus}</span></div>
        <div className="flex items-center gap-1">
          <button className="btn h-[26px] text-[11px] bg-blue-50 border-blue-200 text-blue-700" onClick={() => { setTab('source'); onLocateSql?.(state.selectedEntity); }}>Locate SQL</button>
          <button className="btn h-[26px] text-[11px]" onClick={() => state.selectedOutput && setState((s) => ({ ...s, renderMode: 'current_field_path' }))}>Focus Path</button>
          <button className="btn h-[26px] text-[11px]" onClick={() => setState((s) => ({ ...s, detailMode: 'expanded', detailTab: 'mapping' }))}>View Mapping</button>
          <button className="btn h-[26px] text-[11px]" onClick={() => setState((s) => ({ ...s, detailMode: s.detailMode === 'expanded' ? 'compact' : 'expanded' }))}>{state.detailMode === 'expanded' ? 'Compact' : 'Expand'}</button>
          <button className="btn h-[26px] text-[11px]" onClick={() => setState((s) => ({ ...s, detailMode: 'collapsed' }))}>Close</button>
        </div>
      </div>
      <div className="detail-body">
        <div className="tabs">
          {(['summary', 'mapping', 'source', 'diagnostics', 'semantics'] as DetailTab[]).map((tab) => <button key={tab} className={cx('tab', state.detailTab === tab && 'active')} onClick={() => setTab(tab)}>{tab}</button>)}
        </div>
        <div className="detail-content">{body}</div>
      </div>
    </div>
  );
}

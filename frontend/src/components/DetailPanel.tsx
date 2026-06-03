import type React from 'react';
import { mappings, sourceLocations as mockSourceLocations } from '../data/mockLineage';
import { diagnosticsForEntity, entityName, entityOf, buildPathContext } from '../data/selectors';
import type { DetailTab, Diagnostic, EdgeMapping, WorkbenchState } from '../types/lineage';
import { cx } from '../utils/cx';

interface Props {
  state: WorkbenchState;
  setState: React.Dispatch<React.SetStateAction<WorkbenchState>>;
  /** Called when user clicks "Locate SQL" → navigate Monaco to entity's range */
  onLocateSql?: (entityId: string) => void;
}

function K({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="kv"><div className="kv-label">{label}</div><div className="kv-value">{value}</div></div>;
}

function DiagnosticCard({ diagnostic }: { diagnostic: Diagnostic }) {
  return <div className={cx('card diag', diagnostic.severity)}><div className="card-title">{diagnostic.code}</div><b>Reason:</b> {diagnostic.reason}<br /><b>Impact:</b> {diagnostic.impact}<br /><b>Action:</b> {diagnostic.action}</div>;
}

function MappingList({ items }: { items: EdgeMapping[] }) {
  if (!items.length) return <div className="card">No direct mapping. Default subquery view is structural.</div>;
  return <div className="cards">{items.map((m) => <div key={m.id} className="card"><div className="card-title">{m.id}</div><K label="source → target" value={`${entityName(m.source)} → ${entityName(m.target)}`} /><K label="relation" value={m.relation} /><K label="confidence" value={m.confidence} /></div>)}</div>;
}

export function DetailPanel({ state, setState, onLocateSql }: Props) {
  const entity = entityOf(state.selectedEntity) ?? { id: state.selectedEntity, type: 'unknown', name: state.selectedEntity, comment: '暂无实体信息。' };
  // fallback: use mock mappings when backend doesn't provide EdgeMapping list
  const mapping = state.selectedMapping ? mappings.find((x) => x.id === state.selectedMapping) : undefined;
  const related = mapping ? [mapping] : mappings.filter((x) => x.source === state.selectedEntity || x.target === state.selectedEntity || x.expression === state.selectedEntity);
  // Use state.sourceLocations (from backend analysis) when available, fallback to mock
  const sourceLocs = state.sourceLocations ?? mockSourceLocations;
  const loc = sourceLocs[state.selectedEntity];
  const pc = buildPathContext(state);

  let body: React.ReactNode;
  if (state.detailMode !== 'expanded') {
    const first = related[0];
    const line1 = mapping ? `${entityName(mapping.source)} → ${entityName(mapping.target)} · ${mapping.relation} · ${mapping.confidence}` : `${entity.name} · ${entity.type} · ${state.selectedOutput ? pc.confidence : 'structure'}`;
    const line2 = first ? `source: ${entityName(first.source)} → target: ${entityName(first.target)} · ${first.relation}` : `Upstream structure · ${diagnosticsForEntity(state, state.selectedEntity).length} diagnostics`;
    body = <div className="compact-lines"><K label="Selected" value={line1} /><K label="Mapping" value={line2} /><K label="SQL" value={loc ? `line ${loc.line} · ${loc.rangeType}` : 'location unavailable'} /></div>;
  } else if (state.detailTab === 'summary') {
    body = <div className="grid"><K label="entity" value={state.selectedEntity} /><K label="name" value={entity.name} /><K label="comment" value={entity.comment} /></div>;
  } else if (state.detailTab === 'mapping') {
    body = <MappingList items={related} />;
  } else if (state.detailTab === 'source') {
    body = <div className="grid"><K label="location" value={loc ? `line ${loc.line}, col ${loc.col}` : 'unavailable'} /><K label="range_type" value={loc?.rangeType || 'unavailable'} /><K label="guard" value={state.trustStatus === 'trusted' ? 'exact if range exact' : 'blocked by stale/untrusted'} /></div>;
  } else if (state.detailTab === 'diagnostics') {
    const ds = diagnosticsForEntity(state, state.selectedEntity);
    body = <div className="cards">{(ds.length ? ds : [{ id: 'none', code: 'NO_ENTITY_DIAGNOSTIC', entityId: state.selectedEntity, severity: 'info', reason: '当前实体无诊断。', impact: '无额外风险。', action: '继续查看路径。' } satisfies Diagnostic]).map((d) => <DiagnosticCard key={d.id} diagnostic={d} />)}</div>;
  } else {
    body = <div className="grid"><K label="result_grain" value="country_name" /><K label="filters" value="dt + channel" /><K label="semantic_layer" value="P1 / P2 expanded" /></div>;
  }

  const setTab = (tab: DetailTab) => setState((s) => ({ ...s, detailTab: tab }));

  return (
    <div className={cx('detail', state.detailMode === 'collapsed' && 'collapsed', state.detailMode === 'expanded' && 'expanded')}>
      <div className="detail-head">
        <div className="detail-title"><span className="rail" /><span className="detail-name">{mapping ? mapping.id : entity.name}</span><span className="badge">{mapping ? 'edge_mapping' : entity.type}</span><span className="badge">{state.trustStatus}</span></div>
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

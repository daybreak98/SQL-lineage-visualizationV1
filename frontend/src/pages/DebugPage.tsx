import type React from 'react';
import { buildPathContext, entityName } from '../data/selectors';
import type { Diagnostic, WorkbenchState } from '../types/lineage';

interface Props {
  state: WorkbenchState;
  dialect: string;
  sql: string;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="debug-stat">
      <div className="debug-label">{label}</div>
      <div className="debug-value">{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="debug-section">
      <div className="debug-section-title">{title}</div>
      {children}
    </section>
  );
}

function DiagnosticRow({ diagnostic }: { diagnostic: Diagnostic }) {
  return (
    <div className={`debug-row ${diagnostic.severity}`}>
      <b>{diagnostic.code}</b>
      <span>{diagnostic.severity}</span>
      <span>{diagnostic.entityId}</span>
      <span>{diagnostic.reason}</span>
    </div>
  );
}

export function DebugPage({ state, dialect, sql }: Props) {
  const result = state.lastAnalysisResult;
  const graph = state.backendGraph;
  const pc = buildPathContext(state);
  const diagnostics = state.backendDiagnostics ?? [];
  const stageStatuses = result?.stage_statuses ?? [];
  const summary = result?.summary ?? {};
  const sourceLocationCount = Object.keys(state.sourceLocations ?? {}).length;
  const invalidEdgeCount = state.backendInvalidEdges?.length ?? 0;

  return (
    <div className="debug-page">
      <div className="debug-head">
        <div>
          <div className="debug-title">Debug Mode</div>
          <div className="debug-sub">Analysis Process, API state, diagnostics, and graph internals.</div>
        </div>
        <div className="debug-pills">
          <span className="pill">{dialect}</span>
          <span className="pill">{state.pageMode} | {state.analysisStatus} | {state.trustStatus}</span>
        </div>
      </div>

      <div className="debug-grid">
        <Stat label="schema" value={result?.schema_version ?? 'not analyzed'} />
        <Stat label="analysis_id" value={result?.analysis_id ?? '-'} />
        <Stat label="elapsed_ms" value={result?.elapsed_ms ?? '-'} />
        <Stat label="sql_chars" value={sql.length} />
        <Stat label="graph_nodes" value={graph?.nodes.length ?? 0} />
        <Stat label="graph_edges" value={graph?.edges.length ?? 0} />
        <Stat label="diagnostics" value={diagnostics.length} />
        <Stat label="source_locations" value={sourceLocationCount} />
      </div>

      <div className="debug-columns">
        <Section title="Analysis Process">
          <div className="debug-kv"><b>backend_message</b><span>{state.backendMessage ?? 'No backend message yet.'}</span></div>
          <div className="debug-kv"><b>last_transition</b><span>{state.lastTransition ?? 'initial'}</span></div>
          <div className="debug-kv"><b>render_mode</b><span>{state.renderMode}</span></div>
          <div className="debug-kv"><b>graph_view</b><span>{state.graphViewMode}</span></div>
          <div className="debug-kv"><b>selected</b><span>{entityName(state.selectedEntity)}</span></div>
          <div className="debug-kv"><b>output</b><span>{state.selectedOutput ? entityName(state.selectedOutput) : 'none'}</span></div>
          <div className="debug-kv"><b>path_context</b><span>{pc.status} | nodes {pc.nodes} | warnings {pc.warnings}</span></div>
          <div className="debug-kv"><b>invalid_edges</b><span>{invalidEdgeCount}</span></div>
        </Section>

        <Section title="API Errors">
          {state.lastApiError ? (
            <div className="debug-error">{state.lastApiError}</div>
          ) : (
            <div className="debug-empty">No API error recorded for the latest operation.</div>
          )}
        </Section>
      </div>

      <div className="debug-columns">
        <Section title="Stage Statuses">
          {stageStatuses.length ? stageStatuses.map((stage) => (
            <div key={stage.stage} className="debug-row">
              <b>{stage.stage}</b>
              <span>{stage.status}</span>
              <span>{stage.elapsed_ms}ms</span>
              <span>{stage.diagnostic_codes.length ? stage.diagnostic_codes.join(', ') : 'no diagnostics'}</span>
            </div>
          )) : <div className="debug-empty">No stage statuses returned by backend.</div>}
        </Section>

        <Section title="Diagnostics">
          {diagnostics.length ? diagnostics.map((diagnostic) => (
            <DiagnosticRow key={diagnostic.id} diagnostic={diagnostic} />
          )) : <div className="debug-empty">No diagnostics in current analysis.</div>}
        </Section>
      </div>

      <div className="debug-columns">
        <Section title="Extracted Objects">
          <div className="debug-kv"><b>tables</b><span>{result?.tables_extracted?.join(', ') || '-'}</span></div>
          <div className="debug-kv"><b>columns</b><span>{result?.columns_extracted?.join(', ') || '-'}</span></div>
          <div className="debug-kv"><b>unsupported</b><span>{result?.unsupported_features?.join(', ') || '-'}</span></div>
        </Section>

        <Section title="Backend Summary">
          <pre className="debug-pre">{JSON.stringify(summary, null, 2)}</pre>
        </Section>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import type React from 'react';
import { buildPathContext } from '../data/selectors';
import type { SearchItem, WorkbenchState } from '../types/lineage';
import { cx } from '../utils/cx';

interface Props {
  state: WorkbenchState;
  setState: React.Dispatch<React.SetStateAction<WorkbenchState>>;
  onSelectResult: (item: SearchItem) => void;
}

export function SearchBar({ state, setState, onSelectResult }: Props) {
  const canSearch = state.pageMode === 'analyzed' && state.trustStatus === 'trusted';
  const q = state.query.trim().toLowerCase();
  const defaultItems = state.backendSearchItems ?? [];
  const allItems = state.backendSearchItems ?? [];
  let items = q
    ? allItems.filter((item) => `${item.displayName} ${item.sub} ${item.reason}`.toLowerCase().includes(q))
    : defaultItems;

  if (state.scope !== 'all') {
    const scopedItems = state.scope === 'cte'
      ? items.filter((item) => item.entityId.startsWith('cte:'))
      : items.filter((item) => item.type === state.scope);
    items = scopedItems;
  }

  const pc = buildPathContext(state);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchbarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!searchOpen) return;

    const handleDocumentMouseDown = (event: MouseEvent) => {
      if (searchbarRef.current && !searchbarRef.current.contains(event.target as Node)) {
        setSearchOpen(false);
      }
    };

    document.addEventListener('mousedown', handleDocumentMouseDown);
    return () => document.removeEventListener('mousedown', handleDocumentMouseDown);
  }, [searchOpen]);

  const handleSelect = (item: SearchItem) => {
    setSearchOpen(false);
    setState((s) => ({ ...s, query: '' }));
    onSelectResult(item);
  };

  return (
    <div className="searchbar" ref={searchbarRef}>
      <div className="search-wrap">
        <span className="text-slate-400">⌕</span>
        <input
          id="fieldSearch"
          disabled={!canSearch}
          placeholder="Search field, table, alias..."
          value={state.query}
          onFocus={() => {
            if (canSearch) {
              setSearchOpen(true);
              setState((s) => ({ ...s, drawerOpen: s.drawerOpen }));
            }
          }}
          onChange={(event) => {
            setState((s) => ({ ...s, query: event.target.value }));
            if (canSearch) setSearchOpen(true);
          }}
        />
        {state.query && <button className="btn h-[22px] px-1.5" onClick={() => setState((s) => ({ ...s, query: '' }))}>Clear</button>}
      </div>
      <select className="select h-8" disabled={!canSearch} value={state.scope} onChange={(event) => setState((s) => ({ ...s, scope: event.target.value }))}>
        <option value="all">All</option><option value="output">Output</option><option value="source">Source</option><option value="cte">CTE</option><option value="subquery">Subquery</option>
      </select>
      <button className={cx('output-capsule', !state.selectedOutput && 'idle', pc.status === 'stale' && 'stale', pc.status === 'partial' && 'partial', pc.status === 'low_confidence' && 'low')} onClick={() => setState((s) => ({ ...s, query: '', scope: 'output' }))}>
        <span className={cx('dot', state.trustStatus !== 'trusted' && 'stale')} />
        <span className="name">{pc.display}</span>
        <span className="meta">· {pc.status === 'ready' ? `${pc.warnings}⚠` : pc.status === 'idle' ? 'none' : pc.status}</span>
      </button>
      <span className={cx('pill', state.trustStatus === 'trusted' ? 'trusted' : 'stale')}>{state.trustStatus === 'stale' ? 'stale' : `${items.length} results`}</span>

      {canSearch && searchOpen && (
        <div className="popover open">
          <div className="popover-head">
            <button className="btn h-[22px] px-1.5 text-[10px]" onClick={() => setSearchOpen(false)}>✕ Close</button>
            <span>{q ? 'Backend parse results' : 'Backend fields from analyze'}</span>
          </div>
          <div>
            {items.length ? items.map((item) => (
              <button key={item.itemId} className="result" onClick={() => handleSelect(item)}>
                <span className="min-w-0"><span className="result-title">{item.warning && <span className="dot warn" />}{item.displayName}</span><span className="result-sub">{item.sub}</span></span>
                <span className="reason" style={item.warning ? { color: 'var(--red)' } : undefined}>{item.reason}</span>
              </button>
            )) : <div className="card">No backend search results for the current analysis.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

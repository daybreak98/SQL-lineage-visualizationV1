import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { ArrowUpToLine, Info, LocateFixed } from 'lucide-react';

function useHint(enabled = true) {
  const id = useId();
  const [hover, setHover] = useState(false), [focus, setFocus] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const visible = enabled && (hover || focus) && !dismissed;
  useEffect(() => {
    if (!visible) return;
    function escape(event: KeyboardEvent) { if (event.key === 'Escape') setDismissed(true); }
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [visible]);
  const dismiss = useCallback(() => setDismissed(true), []);
  return { id, visible, dismiss, hoverEvents: {
    onMouseEnter: () => { setHover(true); setDismissed(false); },
    onMouseLeave: () => setHover(false),
  }, focusEvents: {
    onFocus: () => { setFocus(true); setDismissed(false); },
    onBlur: () => setFocus(false),
    'aria-describedby': visible ? id : undefined,
  } };
}

export function DetailHelp({ label, children }: { label: string; children: string }) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null), trigger = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const hint = useHint(!open), { dismiss } = hint;
  useEffect(() => {
    if (!open) return;
    closeButton.current?.focus();
    function close() { setOpen(false); trigger.current?.focus(); dismiss(); }
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) close();
    }
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.stopPropagation(); close(); }
    }
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open, dismiss]);
  return <span className="j-annotation" ref={root} {...hint.hoverEvents}>
    <button type="button" ref={trigger} className="btn j-icon-action" aria-label={label}
      aria-expanded={open} aria-controls={panelId} {...hint.focusEvents}
      onClick={() => { hint.dismiss(); setOpen(!open); }}><Info aria-hidden="true" size={16} /></button>
    {hint.visible && <span id={hint.id} className="j-tooltip" role="tooltip">{children}</span>}
    <span hidden={!open} id={panelId} className="j-help-popover" role="group" aria-label={label}>
      <span>{children}</span>
      <button type="button" className="btn" ref={closeButton}
        onClick={() => { setOpen(false); trigger.current?.focus(); hint.dismiss(); }}>关闭说明</button>
    </span>
  </span>;
}

export function LocateAction({ label, onClick, producer = false }: { label: string; onClick: () => void; producer?: boolean }) {
  const hint = useHint();
  const Icon = producer ? ArrowUpToLine : LocateFixed;
  const { 'aria-describedby': _duplicateLabel, ...focusEvents } = hint.focusEvents;
  return <span className="j-annotation" {...hint.hoverEvents}>
    <button type="button" className="btn j-icon-action" aria-label={label} {...focusEvents}
      onClick={() => { hint.dismiss(); onClick(); }}><Icon aria-hidden="true" size={16} /></button>
    {hint.visible && <span className="j-tooltip" aria-hidden="true">{label}</span>}
  </span>;
}

import { useEffect, useState } from 'react';
import type { RefObject } from 'react';
import { cx } from '../utils/cx';

interface Props {
  split: number;
  measureRef?: RefObject<HTMLElement | null>;
  label?: string;
  setSplit: (value: number) => void;
}

export function Splitter({ split, setSplit, measureRef, label = 'Resize SQL and Canvas panels' }: Props) {
  const [dragging, setDragging] = useState(false);
  const [start, setStart] = useState({ x: 0, split });

  useEffect(() => {
    const move = (event: MouseEvent) => {
      if (!dragging) return;
      const workspace = measureRef?.current ?? document.getElementById('workspace');
      const width = workspace?.getBoundingClientRect().width || window.innerWidth;
      const next = Math.max(24, Math.min(62, start.split + ((event.clientX - start.x) / width) * 100));
      setSplit(next);
    };
    const up = () => setDragging(false);
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    return () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
  }, [dragging, measureRef, setSplit, start]);

  return (
    <div className="splitter-zone">
      {dragging && <div className="overlay show" />}
      <button
        className={cx('splitter', dragging && 'dragging')}
        aria-label={label}
        onMouseDown={(event) => {
          event.preventDefault();
          setStart({ x: event.clientX, split });
          setDragging(true);
        }}
        onDoubleClick={() => setSplit(split > 40 ? 30 : 44)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft') setSplit(Math.max(24, split - 2));
          if (event.key === 'ArrowRight') setSplit(Math.min(62, split + 2));
        }}
      >
        <span className="splitter-line" />
      </button>
      <div className={cx('split-tooltip', dragging && 'show')}>SQL {Math.round(split)}% / Canvas {Math.round(100 - split)}%</div>
    </div>
  );
}

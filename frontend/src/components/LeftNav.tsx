import { cx } from '../utils/cx';

const items: Array<[string, string, string]> = [
  ['workbench', 'W', 'Workbench'],
  ['convert', 'C', 'Dialect Convert'],
  ['render', 'R', 'RenderMode'],
  ['taxonomy', 'N', 'Taxonomy'],
  ['snapshots', 'S', 'Snapshots'],
  ['diagnostics', '!', 'Diagnostics'],
];

interface Props {
  active: string;
  onOpen: (tab: string) => void;
}

export function LeftNav({ active, onOpen }: Props) {
  return (
    <aside className="leftnav">
      {items.map(([key, label, title]) => (
        <button
          key={key}
          title={title}
          className={cx('nav-btn', active === key && 'active')}
          onClick={() => onOpen(key)}
        >
          {label}
        </button>
      ))}
    </aside>
  );
}

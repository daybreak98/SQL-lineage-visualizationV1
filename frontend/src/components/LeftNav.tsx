import { cx } from '../utils/cx';

const items = [
  ['workbench', 'W', 'Workbench'],
  ['subfield', 'J', '亚字段血缘解析'],
  ['convert', 'C', 'Dialect Convert'],
] as const;

export type WorkbenchView = typeof items[number][0];

interface Props {
  active: WorkbenchView;
  onOpen: (tab: WorkbenchView) => void;
}

export function LeftNav({ active, onOpen }: Props) {
  return (
    <nav className="leftnav" aria-label="工作台导航">
      {items.map(([key, label, title]) => (
        <button
          key={key}
          type="button"
          title={title}
          aria-label={title}
          aria-current={active === key ? 'page' : undefined}
          className={cx('nav-btn', active === key && 'active')}
          onClick={() => onOpen(key)}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LeftNav } from '../LeftNav';

describe('LeftNav', () => {
  it('only exposes the main, dialect convert, and debug page entries', () => {
    render(<LeftNav active="workbench" onOpen={vi.fn()} />);

    expect(screen.getByTitle('Workbench')).toBeInTheDocument();
    expect(screen.getByTitle('Dialect Convert')).toBeInTheDocument();
    expect(screen.getByTitle('Debug Mode')).toBeInTheDocument();
    expect(screen.queryByTitle('RenderMode')).toBeNull();
    expect(screen.queryByTitle('Taxonomy')).toBeNull();
    expect(screen.queryByTitle('Snapshots')).toBeNull();
    expect(screen.queryByTitle('Diagnostics')).toBeNull();
  });
});

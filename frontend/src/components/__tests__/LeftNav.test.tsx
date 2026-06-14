import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LeftNav } from '../LeftNav';

describe('LeftNav', () => {
  it('only exposes the main and dialect convert entries', () => {
    render(<LeftNav active="workbench" onOpen={vi.fn()} />);

    expect(screen.getByTitle('Workbench')).toBeInTheDocument();
    expect(screen.getByTitle('Dialect Convert')).toBeInTheDocument();
    expect(screen.queryByTitle('Debug Mode')).toBeNull();
    expect(screen.queryByTitle('RenderMode')).toBeNull();
    expect(screen.queryByTitle('Taxonomy')).toBeNull();
    expect(screen.queryByTitle('Snapshots')).toBeNull();
    expect(screen.queryByTitle('Diagnostics')).toBeNull();
  });
});

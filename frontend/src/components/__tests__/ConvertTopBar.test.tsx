import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ConvertTopBar } from '../ConvertTopBar';

describe('ConvertTopBar', () => {
  it('shows backend online for any resolved backend version string', () => {
    const { container } = render(<ConvertTopBar backendStatus="Backend: 1.2.3" />);
    expect(screen.getByText('SQL Dialect Convert')).toBeInTheDocument();
    expect(container.querySelector('.dot.online')).not.toBeNull();
  });

  it('shows backend offline for offline status', () => {
    const { container } = render(<ConvertTopBar backendStatus="Backend: offline" />);
    expect(container.querySelector('.dot.offline')).not.toBeNull();
  });
});

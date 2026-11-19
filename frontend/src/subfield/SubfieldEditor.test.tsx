import { render, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { expect, it, vi } from 'vitest';
import SubfieldEditor from './SubfieldEditor';
import { createSQLPositionIndex } from './sqlPositionIndex';

const instance = vi.hoisted(() => ({
  updateOptions: vi.fn(), onKeyDown: vi.fn(() => ({ dispose() {} })),
  getModel: vi.fn(() => ({ getValue: () => "SELECT '$.a'" })),
  getSelection: vi.fn(), setSelection: vi.fn(), setPosition: vi.fn(),
  revealLineInCenter: vi.fn(), focus: vi.fn(),
}));
vi.mock('../components/SqlEditorPanel', () => ({ SqlEditorPanel: ({ onEditorMounted }: {
  onEditorMounted: (editor: typeof instance) => void;
}) => { useEffect(() => onEditorMounted(instance), [onEditorMounted]); return null; } }));

it.each([true, false])('clears an invalidated evidence selection only if it is still active (%s)', async stillActive => {
  vi.clearAllMocks();
  const sql = "SELECT '$.a'";
  const index = createSQLPositionIndex(sql);
  const props = { sql, dialect: 'spark', busy: false, run: vi.fn(), setSql: vi.fn(), positionIndex: index };
  const { rerender } = render(<SubfieldEditor {...props} locate={{ start: 7, end: 12 }} />);
  const expectedRange = { startLineNumber: 1, startColumn: 8, endLineNumber: 1, endColumn: 13 };
  await waitFor(() => expect(instance.setSelection).toHaveBeenCalledWith(expectedRange));
  const cursor = { lineNumber: 1, column: 13 };
  const equalsRange = vi.fn(() => stillActive);
  instance.getSelection.mockReturnValue({ equalsRange, getPosition: () => cursor });
  rerender(<SubfieldEditor {...props} locate={null} />);
  expect(equalsRange).toHaveBeenCalledWith(expectedRange);
  if (stillActive) expect(instance.setPosition).toHaveBeenCalledWith(cursor);
  else expect(instance.setPosition).not.toHaveBeenCalled();
});

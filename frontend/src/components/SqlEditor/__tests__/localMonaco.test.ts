import { beforeEach, describe, expect, it, vi } from 'vitest';

const configMock = vi.fn();
const workerConstructor = vi.fn();
const localMonaco = { editor: { create: vi.fn() } };

vi.mock('@monaco-editor/react', () => ({
  loader: { config: configMock },
}));

vi.mock('monaco-editor', () => localMonaco);

vi.mock('monaco-editor/esm/vs/editor/editor.worker?worker', () => ({
  default: class LocalEditorWorker {
    constructor() {
      workerConstructor();
    }
  },
}));

describe('configureLocalMonaco', () => {
  beforeEach(() => {
    vi.resetModules();
    configMock.mockClear();
    workerConstructor.mockClear();
    delete (globalThis as typeof globalThis & { MonacoEnvironment?: unknown }).MonacoEnvironment;
  });

  it('binds the React loader and editor worker to local bundled modules', async () => {
    const { configureLocalMonaco } = await import('../localMonaco');

    configureLocalMonaco();

    expect(configMock).toHaveBeenCalledWith({ monaco: localMonaco });
    expect(globalThis.__SQL_LINEAGE_MONACO__?.editor).toBe(localMonaco.editor);
    expect(configMock).not.toHaveBeenCalledWith(
      expect.objectContaining({ paths: expect.anything() }),
    );

    const environment = (
      globalThis as typeof globalThis & {
        MonacoEnvironment?: { getWorker: () => Worker };
      }
    ).MonacoEnvironment;
    expect(environment).toBeDefined();

    environment?.getWorker();
    expect(workerConstructor).toHaveBeenCalledOnce();
  });

  it('configures the loader only once per application session', async () => {
    const { configureLocalMonaco } = await import('../localMonaco');

    configureLocalMonaco();
    configureLocalMonaco();

    expect(configMock).toHaveBeenCalledOnce();
  });
});

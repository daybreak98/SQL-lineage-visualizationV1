import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
import LocalEditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';

type MonacoWorkerEnvironment = {
  getWorker: (_moduleId: string, _label: string) => Worker;
};

declare global {
  var __SQL_LINEAGE_MONACO__: typeof monaco | undefined;
}

let configured = false;

export function configureLocalMonaco() {
  if (configured) return;

  (
    globalThis as typeof globalThis & {
      MonacoEnvironment?: MonacoWorkerEnvironment;
    }
  ).MonacoEnvironment = {
    getWorker: () => new LocalEditorWorker(),
  };

  loader.config({ monaco });
  if (import.meta.env.DEV) {
    globalThis.__SQL_LINEAGE_MONACO__ = monaco;
  }
  configured = true;
}

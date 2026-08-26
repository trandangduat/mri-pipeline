import {save} from '@tauri-apps/plugin-dialog';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';

export interface SaveJsonResult {
  ok: boolean;
  cancelled?: boolean;
  path?: string;
  error?: string;
}

function isTauri(): boolean {
  return typeof window !== 'undefined' && Boolean((window as unknown as {__TAURI_INTERNALS__?: unknown}).__TAURI_INTERNALS__);
}

/** Suggested file name like "neuroflow-preset-20260826-1651.json". */
export function defaultConfigName(prefix: string): string {
  const safePrefix = String(prefix || 'config').replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'config';
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
  return `${safePrefix}-${stamp}.json`;
}

/**
 * Ask the user where to save a JSON payload via the native save dialog and
 * write it through the backend (which redacts password fields).
 * Falls back to a browser download when not running inside Tauri.
 */
export async function saveJsonAsDialog(
  defaultFileName: string,
  data: Record<string, unknown>,
): Promise<SaveJsonResult> {
  let targetPath: string | null;
  if (isTauri()) {
    try {
      targetPath = await save({
        defaultPath: defaultFileName,
        filters: [{name: 'JSON', extensions: ['json']}],
      });
    } catch (error: unknown) {
      return {ok: false, error: (error as Error).message || 'Could not open save dialog.'};
    }
    if (!targetPath) return {ok: false, cancelled: true};
  } else {
    // Plain browser (vite dev outside Tauri): download the blob directly.
    try {
      const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = defaultFileName.endsWith('.json') ? defaultFileName : `${defaultFileName}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      return {ok: true, path: anchor.download};
    } catch (error: unknown) {
      return {ok: false, error: (error as Error).message || 'Download failed.'};
    }
  }

  try {
    const res = await new BackendClient(DEFAULT_BACKEND_URL).exportConfig(targetPath, data);
    if (!res.ok) return {ok: false, error: res.error || 'Could not save file.'};
    return {ok: true, path: res.path || targetPath};
  } catch (error: unknown) {
    return {ok: false, error: (error as Error).message || 'Could not save file.'};
  }
}

export interface PresetMetadataLike {
  stage_order?: string[] | null;
}

export interface PresetFormValuesLike {
  pipelineMode?: string;
  [key: string]: unknown;
}

/** Build the preset payload matching what Load Preset reads (`selected_tools`). */
export function buildPresetPayload(
  metadata: PresetMetadataLike | null | undefined,
  formValues: PresetFormValuesLike,
): Record<string, unknown> {
  const selectedTools: Record<string, string> = {};
  for (const stage of metadata?.stage_order || []) {
    const toolKey = formValues[`stage_${stage}`];
    if (typeof toolKey === 'string' && toolKey) selectedTools[stage] = toolKey;
  }
  return {
    type: 'mri-pipeline-preset',
    pipeline_mode: formValues.pipelineMode || 'Custom',
    selected_tools: selectedTools,
  };
}

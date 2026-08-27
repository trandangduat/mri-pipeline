import {describe, expect, test, vi, afterEach} from 'vitest';
import {buildPresetPayload, defaultConfigName} from '../src/lib/configExport';

const saveDialogMock = vi.fn();
vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(),
  save: (...args: unknown[]) => saveDialogMock(...args),
}));

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  delete (window as unknown as {__TAURI_INTERNALS__?: unknown}).__TAURI_INTERNALS__;
  saveDialogMock.mockReset();
  fetchMock.mockReset();
});

describe('defaultConfigName', () => {
  test('embeds prefix and a date-time stamp with .json extension', () => {
    const name = defaultConfigName('neuroflow-preset');
    expect(name).toMatch(/^neuroflow-preset-\d{8}-\d{4}\.json$/);
  });

  test('sanitizes unsafe prefix characters', () => {
    expect(defaultConfigName('--my preset v1!!')).toMatch(/^my-preset-v1-\d{8}-\d{4}\.json$/);
    expect(defaultConfigName('')).toMatch(/^config-\d{8}-\d{4}\.json$/);
  });
});

describe('buildPresetPayload', () => {
  test('collects selected stage tools and pipeline mode', () => {
    const payload = buildPresetPayload(
      {stage_order: ['segmentation', 'registration', 'stats']},
      {pipelineMode: 'Custom', stage_segmentation: 'synthseg', stage_stats: 'cat12_stats', stage_registration: ''},
    );
    expect(payload).toEqual({
      type: 'mri-pipeline-preset',
      pipeline_mode: 'Custom',
      selected_tools: {segmentation: 'synthseg', stats: 'cat12_stats'},
    });
  });

  test('returns empty selected_tools when nothing is chosen', () => {
    const payload = buildPresetPayload({stage_order: ['segmentation']}, {pipelineMode: 'Custom'});
    expect(payload.selected_tools).toEqual({});
  });

  test('handles missing metadata gracefully', () => {
    const payload = buildPresetPayload(null, {pipelineMode: 'FastSurfer'});
    expect(payload).toEqual({
      type: 'mri-pipeline-preset',
      pipeline_mode: 'FastSurfer',
      selected_tools: {},
    });
  });
});

describe('saveJsonAsDialog', () => {
  test('writes via backend export endpoint at the chosen path', async () => {
    (window as unknown as {__TAURI_INTERNALS__?: unknown}).__TAURI_INTERNALS__ = {};
    saveDialogMock.mockResolvedValue('/home/tester/neuroflow-preset.json');
    fetchMock.mockResolvedValue({ok: true, json: async () => ({ok: true, path: '/home/tester/neuroflow-preset.json'})});
    globalThis.fetch = fetchMock;

    const {saveJsonAsDialog} = await import('../src/lib/configExport');
    const result = await saveJsonAsDialog('neuroflow-preset.json', {selected_tools: {}});

    expect(result.ok).toBe(true);
    expect(result.path).toBe('/home/tester/neuroflow-preset.json');
    const exportCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/config/export'));
    expect(exportCall).toBeDefined();
    const body = JSON.parse(String(exportCall?.[1]?.body));
    expect(body.path).toBe('/home/tester/neuroflow-preset.json');
    expect(body.data).toEqual({selected_tools: {}});
  });

  test('reports cancelled when the dialog is dismissed', async () => {
    (window as unknown as {__TAURI_INTERNALS__?: unknown}).__TAURI_INTERNALS__ = {};
    saveDialogMock.mockResolvedValue(null);
    globalThis.fetch = fetchMock;

    const {saveJsonAsDialog} = await import('../src/lib/configExport');
    const result = await saveJsonAsDialog('neuroflow-preset.json', {});

    expect(result.ok).toBe(false);
    expect(result.cancelled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('falls back to a browser download outside Tauri', async () => {
    globalThis.fetch = fetchMock;
    const anchors: Array<{href: string; download: string; click: ReturnType<typeof vi.fn>}> = [];
    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        const anchor = {href: '', download: '', click: vi.fn()};
        anchors.push(anchor);
        return anchor as unknown as HTMLAnchorElement;
      }
      return document.createElement(tag);
    });
    const createObjectURL = vi.fn(() => 'blob:mock');
    const revokeObjectURL = vi.fn();
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL;

    try {
      const {saveJsonAsDialog} = await import('../src/lib/configExport');
      const result = await saveJsonAsDialog('neuroflow-workspace.json', {version: 1});

      expect(result.ok).toBe(true);
      expect(anchors.length).toBe(1);
      expect(anchors[0].download).toBe('neuroflow-workspace.json');
      expect(anchors[0].click).toHaveBeenCalled();
      expect(createObjectURL).toHaveBeenCalled();
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock');
    } finally {
      createElementSpy.mockRestore();
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
    }
  });
});

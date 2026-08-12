import React from 'react';
import {Container, Download, RefreshCw, Search, Terminal, Trash2} from 'lucide-react';
import {Panel, Button, inputCls, StatusPill} from '../components/ui';
import {
  filterImages,
  imageRowKey,
  selectAllVisible,
  unselectVisible,
  selectMissing,
  toggleImageKey,
  isImageInstalled,
} from '../lib/tools';
import type {ToolImage} from '../types/backend';
import {useEnvironment, useMetadata} from '../query/useEnvironment';
import {useLocalImageStatusMutation} from '../query/useTools';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useToolsStore} from '../stores/toolsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUiStore} from '../stores/uiStore';
import {buildRemotePayload} from '../api/runConfig';

export function ToolsPage() {
  const {data: environment, refetch: refetchEnvironment} = useEnvironment();
  const {data: metadata} = useMetadata();

  const formValues = usePipelineFormStore((s) => s.formValues);
  const remoteResult = useRemoteStore();

  const latestImages = useToolsStore((s) => s.latestImages);
  const setLatestImages = useToolsStore((s) => s.setLatestImages);
  const imageSearch = useToolsStore((s) => s.imageSearch);
  const setImageSearch = useToolsStore((s) => s.setImageSearch);
  const imageSelection = useToolsStore((s) => s.imageSelection);
  const setImageSelection = useToolsStore((s) => s.setImageSelection);
  const toolMessage = useToolsStore((s) => s.toolMessage);
  const setToolMessage = useToolsStore((s) => s.setToolMessage);
  const imageLogText = useToolsStore((s) => s.imageLogText);
  const appendImageLog = useToolsStore((s) => s.appendImageLog);

  const busy = useUiStore((s) => s.busy);
  const setBusyKey = useUiStore((s) => s.setBusyKey);

  const selectedRuntimeTarget = () => (formValues.runtimeTarget === 'Server' ? 'Server' : 'Local');

  const python = ((environment as Record<string, unknown> | undefined)?.python as
    {ok?: boolean; path?: string; version?: string} | undefined) || {ok: false, path: '', version: ''};
  const images = filterImages((latestImages || []) as ToolImage[], imageSearch);
  const selectedCount = imageSelection.size;
  const allVisibleSelected = images.length > 0 && images.every((image) => imageSelection.has(imageRowKey(image, 0)));

  const handleToggleSelectAll = () => {
    if (allVisibleSelected) {
      unselectVisible({images, keys: imageSelection, setKeys: setImageSelection});
    } else {
      selectAllVisible({images, keys: imageSelection, setKeys: setImageSelection});
    }
  };

  const handleSelectMissing = () => {
    selectMissing(images, imageSelection, setImageSelection);
  };

  const localImageStatusMutation = useLocalImageStatusMutation();

  const refreshTools = async () => {
    const target = selectedRuntimeTarget();
    if (target === 'Server' && !remoteResult.connected) {
      setToolMessage('Connect SSH before checking server Docker images.');
      appendImageLog('Skipped Server Docker image refresh: SSH is not connected.');
      return;
    }
    const selectedTools = metadata?.presets?.[formValues.pipelineMode]?.tools || {};
    setToolMessage(`Checking ${target} Docker images...`);
    setBusyKey('refreshTools', true);
    try {
      const result = await localImageStatusMutation.mutateAsync({
        selectedTools,
        options: {
          target,
          remote: target === 'Server' ? buildRemotePayload(formValues) : null,
        },
      });
      if (!result.ok) {
        setToolMessage(result.error || `${target} Docker image check failed.`);
        setLatestImages([]);
        setImageSelection(new Set());
        appendImageLog(`${target} Image status failed: ${result.error || 'unknown error'}`);
        return;
      }
      const imgs = Array.isArray(result.images) ? result.images : [];
      setLatestImages(imgs);
      setImageSelection(new Set());
      appendImageLog(`Refreshed ${imgs.length} ${target} Docker image records.`);
    } catch (error: unknown) {
      setToolMessage(`${target} Docker check failed: ${(error as Error).message || 'unknown error'}`);
      setLatestImages([]);
      setImageSelection(new Set());
      appendImageLog(`${target} Docker check failed: ${(error as Error).message || 'unknown error'}`);
    } finally {
      setBusyKey('refreshTools', false);
    }
  };

  const refreshEnvironment = async () => {
    setBusyKey('checkEnv', true);
    try {
      await refetchEnvironment();
    } finally {
      setBusyKey('checkEnv', false);
    }
  };

  return (
    <div className="grid gap-6">
      <Panel
        icon={
          <span className="inline-grid h-8 w-8 place-items-center rounded-md bg-cursor-timeline-read text-xs font-semibold text-cursor-ink">
            Py
          </span>
        }
        title="Python Environment"
        titleRight={
          <Button
            variant="primary"
            icon={<RefreshCw className="h-4 w-4" />}
            onClick={refreshEnvironment}
            disabled={busy.checkEnv}
          >
            Check Environment
          </Button>
        }
      >
        <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(14rem,1fr))]">
          <div className="flex flex-col gap-2 rounded-xl border border-cursor-hairline bg-white p-4">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Runtime Target</span>
            <div className="flex min-w-0 items-center">
              <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-hairline-soft px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-ink">
                {selectedRuntimeTarget()}
              </span>
            </div>
          </div>
          <div className="flex flex-col gap-2 rounded-xl border border-cursor-hairline bg-white p-4">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Python Status</span>
            <div className="flex min-w-0 items-center">
              <StatusPill state={python.ok ? 'installed' : 'missing'}>
                {python.ok ? `Ready (${python.version || 'unknown'})` : 'Missing'}
              </StatusPill>
            </div>
          </div>
          <div className="flex flex-col gap-2 rounded-xl border border-cursor-hairline bg-white p-4">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Executable Path</span>
            <div className="flex min-w-0 items-center">
              <code className="w-full truncate rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft px-2.5 py-1 font-mono text-xs text-cursor-ink">
                {python.path || 'Unknown'}
              </code>
            </div>
          </div>
        </div>
      </Panel>

      <Panel
        icon={<Container className="h-5 w-5 text-cursor-primary" />}
        title="Docker Images"
        titleRight={
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center rounded-full border border-cursor-primary/20 bg-cursor-primary/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-primary">
              {selectedRuntimeTarget()}
            </span>
            <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-hairline px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-body">
              {selectedCount} selected
            </span>
            <Button
              id="refreshToolsButton"
              variant="primary"
              icon={<RefreshCw className="h-4 w-4" />}
              onClick={refreshTools}
              disabled={busy.refreshTools}
            >
              Refresh Tool Status
            </Button>
          </div>
        }
      >
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <label className="relative m-0 block w-full max-w-[20rem]">
            <input
              id="imageSearch"
              type="search"
              placeholder="Search images by name or tag..."
              value={imageSearch}
              onChange={(e) => setImageSearch(e.target.value)}
              className={`${inputCls} pr-9`}
            />
            <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cursor-muted" />
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" onClick={handleToggleSelectAll}>
              {allVisibleSelected ? 'Deselect Visible' : 'Select All Visible'}
            </Button>
            <Button variant="ghost" onClick={handleSelectMissing}>
              Select Missing
            </Button>
            <Button
              variant="ghost"
              icon={<Download className="h-4 w-4" />}
              onClick={() =>
                appendImageLog('Pull images action triggered (safety slice notice: pull is simulated/deferred).')
              }
            >
              Pull Images
            </Button>
            <Button
              variant="ghost"
              icon={<Trash2 className="h-4 w-4" />}
              className="text-cursor-semantic-error hover:bg-cursor-canvas-soft"
              onClick={() =>
                appendImageLog(
                  'Remove local images action triggered (safety slice notice: remove is simulated/deferred).',
                )
              }
            >
              Remove Images
            </Button>
          </div>
        </div>

        <div className="mb-4 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3 text-cursor-body">
          {toolMessage}
        </div>

        <div className="overflow-x-auto rounded-xl border border-cursor-hairline bg-white">
          <table className="w-full text-left text-xs font-mono">
            <thead className="border-b border-cursor-hairline bg-cursor-canvas-soft text-[11px] font-semibold uppercase tracking-wider text-cursor-muted">
              <tr>
                <th className="p-3 w-10 text-center">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={(e) => {
                      if (e.target.checked) {
                        selectAllVisible({images, keys: imageSelection, setKeys: setImageSelection});
                      } else {
                        unselectVisible({images, keys: imageSelection, setKeys: setImageSelection});
                      }
                    }}
                  />
                </th>
                <th className="p-3">Stage / Tool</th>
                <th className="p-3">Image Repository & Tag</th>
                <th className="p-3">Status</th>
                <th className="p-3">Size / ID</th>
              </tr>
            </thead>
            <tbody id="toolTableBody" className="divide-y divide-cursor-hairline-soft">
              {images.length ? (
                images.map((imageItem: Record<string, unknown>, index: number) => {
                  const item = imageItem as Record<string, unknown>;
                  const key = imageRowKey(imageItem as unknown as ToolImage, index);
                  const isSelected = imageSelection.has(key);
                  return (
                    <tr key={key} className="hover:bg-cursor-canvas-soft/50">
                      <td className="p-3 text-center">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => setImageSelection(toggleImageKey(imageSelection, key))}
                        />
                      </td>
                      <td className="p-3 font-sans font-medium text-cursor-ink">
                        {(item.stage || item.tool || 'Unknown Stage') as string}
                      </td>
                      <td className="p-3 font-mono text-cursor-ink">
                        {(item.image || item.repository || 'unknown') as string}
                      </td>
                      <td className="p-3">
                        <StatusPill state={isImageInstalled(item) ? 'installed' : 'missing'}>
                          {(item.status as string) || (isImageInstalled(item) ? 'Installed' : 'Missing')}
                        </StatusPill>
                      </td>
                      <td className="p-3 text-cursor-muted">{(item.size || item.id || 'N/A') as string}</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-cursor-body font-sans">
                    No images match the current filter or search criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel icon={<Terminal className="h-5 w-5 text-cursor-primary" />} title="Docker Execution Log">
        <textarea
          id="imageLog"
          readOnly
          value={imageLogText}
          rows={6}
          className="w-full rounded-xl border border-cursor-hairline bg-white p-4 font-mono text-xs text-cursor-ink focus:outline-none"
        />
      </Panel>
    </div>
  );
}

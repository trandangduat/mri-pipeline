import React, {useRef} from 'react';
import {Workflow, FolderInput, FolderOpen, Save, Play, Square, Loader2, FileKey, Upload, SlidersHorizontal, Eye, EyeOff} from 'lucide-react';
import {open} from '@tauri-apps/plugin-dialog';
import {useNavigate} from 'react-router';
import {Panel, Button, inputCls, labelCls} from '../components/ui';
import {Tooltip, TooltipTrigger, TooltipContent, TooltipProvider} from '@/components/ui/tooltip';
import {SplitPaneForm} from '../components/SplitPaneForm';
import {RuntimeSection} from '../components/RuntimeSection';
import {StartPipelineDialog} from '../components/StartPipelineDialog';
import {useStartPipelineStream} from '../hooks/useStartPipelineStream';
import {useMetadata, useClient} from '../query/useEnvironment';
import {useRemoteBrowseMutation, useLocalBrowseMutation} from '../query/useRemote';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useJobsStore} from '../stores/jobsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {buildRunConfig, buildRemotePayload} from '../api/runConfig';
import {normalizeJob, sortJobsByStartedAtDesc} from '../jobFormatters';
import type {RemoteBrowseEntry, RemoteBrowseResponse} from '../types/backend';


function browseJsonFile(inputRef: React.RefObject<HTMLInputElement | null>) {
  if (inputRef.current) inputRef.current.click();
}

function hasTauriInternals() {
  if (typeof window === 'undefined') return false;
  const internals = (window as unknown as {__TAURI_INTERNALS__?: {invoke?: unknown}}).__TAURI_INTERNALS__;
  return typeof internals?.invoke === 'function';
}

function selectedDialogPath(selected: Awaited<ReturnType<typeof open>>) {
  if (Array.isArray(selected)) return selected[0] || '';
  return selected || '';
}

export function PipelineStepsSection() {
  const {data: metadata, isLoading: metaLoading, isError: metaError} = useMetadata();
  const client = useClient();
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);
  const setFormFields = usePipelineFormStore((s) => s.setFormFields);

  const licensePath = usePipelineFormStore((s) => s.formValues.licensePath as string | undefined);
  const licenseFileInput = useRef<HTMLInputElement>(null);
  const [uploadingLicense, setUploadingLicense] = React.useState(false);
  const [showTools, setShowTools] = React.useState(formValues.pipelineMode === 'Custom');

  // Automatically show tools when in Custom mode, hide when built-in preset is selected
  React.useEffect(() => {
    setShowTools(formValues.pipelineMode === 'Custom');
  }, [formValues.pipelineMode]);

  const activeToolsList = React.useMemo(() => {
    if (!metadata?.tools) return [];
    const stageKeys = metadata.stage_order || [];
    const result: string[] = [];
    for (const stage of stageKeys) {
      const toolKey = (formValues as Record<string, unknown>)[`stage_${stage}`] as string | undefined;
      if (toolKey && metadata.tools[toolKey]) {
        result.push(metadata.tools[toolKey].display_name || toolKey);
      }
    }
    return result;
  }, [metadata, formValues]);

  const needsLicense = React.useMemo(() => {
    if (!metadata?.tools) return false;
    const stageKeys = metadata.stage_order || [];
    for (const stage of stageKeys) {
      const toolKey = (formValues as Record<string, unknown>)[`stage_${stage}`] as string | undefined;
      if (toolKey && metadata.tools[toolKey]?.needs_license) return true;
    }
    return false;
  }, [metadata, formValues]);

  const presetFileInput = useRef<HTMLInputElement>(null);

  const print = (label: string, payload: unknown) => {
    const output = useJobsStore.getState().appendOutput;
    output(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  };

  const handlePipelineModeChange = (mode: string) => {
    const preset = metadata?.presets?.[mode];
    if (preset) {
      const formFields: Record<string, string> = {pipelineMode: mode};
      for (const stageKey of metadata?.stage_order || []) {
        formFields[`stage_${stageKey}`] = '';
      }
      for (const [stageKey, toolKey] of Object.entries(preset.tools || {})) {
        formFields[`stage_${stageKey}`] = toolKey;
      }
      setFormFields(formFields);
      setShowTools(false);
    } else {
      setFormField('pipelineMode', mode);
      setShowTools(mode === 'Custom');
    }
  };

  const handleStageToolChange = (stageId: string, toolKey: string) => {
    setShowTools(true);
    if (formValues.pipelineMode === 'Custom') {
      setFormField(`stage_${stageId}`, toolKey);
      return;
    }
    setFormFields({pipelineMode: 'Custom', [`stage_${stageId}`]: toolKey});
  };

  async function handlePresetFile(file?: File | null) {
    if (!file) return;
    try {
      const content = await file.text();
      const preset = JSON.parse(content) as Record<string, unknown>;
      const formFields: Record<string, unknown> = {pipelineMode: 'Custom'};
      if (preset.selected_tools && typeof preset.selected_tools === 'object') {
        for (const [k, v] of Object.entries(preset.selected_tools)) {
          formFields[`stage_${k}`] = v;
        }
      }
      setFormFields(formFields);
      setShowTools(true);
      print('Loaded preset file', {name: file.name, selected_tools: preset.selected_tools});
    } catch (err: unknown) {
      print('Load preset failed', {error: (err as Error).message});
    }
  }

  async function handleBrowserLicenseFile(file?: File | null) {
    if (!file) return;
    setUploadingLicense(true);
    try {
      const result = await client.uploadLicense(file);
      if (!result.ok || !result.path) {
        throw new Error(result.error || 'License upload failed.');
      }
      setFormField('licensePath', result.path);
      print('License uploaded', {name: file.name, path: result.path});
    } catch (err: unknown) {
      print('License upload failed', {error: (err as Error).message});
    } finally {
      setUploadingLicense(false);
    }
  }

  return (
    <Panel
      icon={<Workflow className="h-5 w-5 text-cursor-primary" />}
      title="Pipeline Steps"
      titleRight={
        <Button
          variant="ghost"
          icon={showTools ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          onClick={() => setShowTools((prev) => !prev)}
          className="h-8 px-2.5 text-xs text-cursor-body hover:text-cursor-ink"
        >
          {showTools ? 'Hide Tools' : 'Show Tools'}
        </Button>
      }
      className="min-w-0"
    >
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className={`${labelCls} min-w-[min(100%,14rem)] flex-1`}>
          Pipeline preset
          <select
            id="pipelineMode"
            name="pipelineMode"
            value={formValues.pipelineMode}
            onChange={(e) => handlePipelineModeChange(e.target.value)}
            className={inputCls}
          >
            {(metadata?.pipeline_modes || []).map((mode) => (
              <option key={mode.id} value={mode.id}>
                {mode.id}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="ghost"
            icon={showTools ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            onClick={() => setShowTools((prev) => !prev)}
          >
            {showTools ? 'Hide Tools' : 'Show Tools'}
          </Button>
          <Button variant="ghost" icon={<FolderOpen className="h-4 w-4" />} onClick={() => browseJsonFile(presetFileInput)}>
            Load Preset
          </Button>
          <Button
            variant="ghost"
            icon={<Save className="h-4 w-4" />}
            onClick={() => print('Save preset', {ok: false, error: 'Preset save UI is not wired in this slice.'})}
          >
            Save Preset
          </Button>
        </div>
        <input
          ref={presetFileInput}
          className="hidden"
          type="file"
          accept="application/json,.json"
          onChange={(e) => handlePresetFile(e.target.files?.[0])}
        />
      </div>
      {metaLoading && (
        <div className="rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-6 text-center">
          <span className="text-[13px] text-cursor-muted">Connecting to backend&hellip;</span>
        </div>
      )}
      {metaError && !metaLoading && (
        <div className="rounded-lg border border-cursor-semantic-error/30 bg-cursor-semantic-error/5 px-4 py-5">
          <p className="m-0 text-[13px] font-medium text-cursor-semantic-error">Backend unavailable</p>
          <p className="mt-1 text-[12px] text-cursor-muted">
            The MRI pipeline backend is not running. Start the dev server with{' '}
            <code className="rounded bg-cursor-canvas-soft px-1 font-mono text-[11px] text-cursor-ink">npm run dev</code>{' '}
            from the <code className="rounded bg-cursor-canvas-soft px-1 font-mono text-[11px] text-cursor-ink">tauri-app/</code>{' '}
            directory, which also starts the Python backend on port 8765.
          </p>
        </div>
      )}
      {!metaLoading && !metaError && !showTools && (
        <div className="rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3.5 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-1.5 min-w-0">
            <span className="font-semibold text-cursor-ink mr-1">Active Tools ({activeToolsList.length}):</span>
            {activeToolsList.length === 0 ? (
              <span className="text-cursor-muted italic">No tools selected</span>
            ) : (
              activeToolsList.map((toolName) => (
                <span
                  key={toolName}
                  className="inline-flex items-center rounded-md border border-cursor-hairline bg-white px-2 py-0.5 font-medium text-cursor-body text-[11px]"
                >
                  {toolName}
                </span>
              ))
            )}
          </div>
          <button
            type="button"
            onClick={() => setShowTools(true)}
            className="text-xs font-semibold text-cursor-primary hover:underline cursor-pointer flex-none ml-auto"
          >
            Show Tools →
          </button>
        </div>
      )}
      {!metaLoading && !metaError && showTools && (
        <div className="grid border border-cursor-hairline">
          {(metadata?.stages || []).length === 0 && (
            <div className="px-4 py-6 text-center text-[13px] text-cursor-muted">No pipeline stages found.</div>
          )}
          {(metadata?.stages || []).map((stage) => {
            const tools = metadata?.tools_by_stage?.[stage.id] || [];
            const selectedToolKey = ((formValues as Record<string, unknown>)[`stage_${stage.id}`] as string) || '';
            const isUnavailable = selectedToolKey === '';
            return (
              <div
                key={stage.id}
                className={`grid items-center gap-x-4 gap-y-2 border-b border-cursor-hairline-soft px-4 py-2.5 last:border-b-0 grid-cols-[minmax(12rem,0.55fr)_minmax(14rem,1fr)] max-[1080px]:grid-cols-1 ${isUnavailable ? 'bg-cursor-canvas-soft/70 border-l-2 border-l-cursor-hairline-strong' : 'bg-white'}`}
              >
                <div className="flex min-h-11 items-center">
                  <strong className={`font-semibold text-[13.5px] leading-none ${isUnavailable ? 'text-cursor-muted' : 'text-cursor-ink'}`}>{stage.label}</strong>
                </div>
                <select
                  name={`stage_${stage.id}`}
                  value={selectedToolKey}
                  onChange={(e) => handleStageToolChange(stage.id, e.target.value)}
                  className={`${inputCls} max-[1080px]:w-full ${isUnavailable ? 'opacity-70' : ''}`}
                >
                  <option value="">Not available</option>
                  {tools.map((toolKey) => {
                    const tool = metadata?.tools?.[toolKey];
                    return (
                      <option key={toolKey} value={toolKey}>
                        {tool?.display_name || toolKey}
                      </option>
                    );
                  })}
                </select>
              </div>
            );
          })}
        </div>
      )}
      {needsLicense && (
        <div className="mt-4 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-3">
          <div className="flex items-center gap-2">
            <FileKey className="h-4 w-4 text-cursor-primary" />
            <span className="text-[13px] font-medium text-cursor-ink">FreeSurfer License</span>
          </div>
          <p className="mt-1 mb-2 text-[12px] text-cursor-muted">
            A selected tool requires a FreeSurfer license file. Provide the path to your license.txt.
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={uploadingLicense}
              onClick={async () => {
                if (!hasTauriInternals()) {
                  licenseFileInput.current?.click();
                  return;
                }
                try {
                  const selected = await open({
                    multiple: false,
                    filters: [{name: 'License', extensions: ['txt']}],
                  });
                  const path = selectedDialogPath(selected);
                  if (path) {
                    setFormField('licensePath', path);
                  }
                } catch (err: unknown) {
                  print('License browse failed', {error: (err as Error).message});
                }
              }}
              className="inline-flex h-9 flex-none cursor-pointer items-center gap-2 rounded-lg border border-cursor-hairline bg-white px-3 text-[12px] font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-60"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              {uploadingLicense ? 'Uploading...' : 'Browse'}
            </button>
            <input
              ref={licenseFileInput}
              className="hidden"
              type="file"
              accept=".txt,text/plain"
              onChange={(event) => {
                void handleBrowserLicenseFile(event.target.files?.[0]);
                event.target.value = '';
              }}
            />
            <input
              value={licensePath || ''}
              onChange={(event) => setFormField('licensePath', event.target.value)}
              placeholder="/path/to/license.txt"
              title={licensePath || ''}
              className={`${inputCls} h-9 min-w-0 flex-1 text-[12px]`}
            />
            {licensePath && (
              <button
                type="button"
                onClick={() => setFormField('licensePath', '')}
                className="text-[12px] text-cursor-muted hover:text-cursor-semantic-error"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}

export function StatsAtlasSection() {
  const {data: metadata} = useMetadata();
  const selectedStatsAtlases = usePipelineFormStore((s) => s.selectedStatsAtlases);
  const removeAtlasStore = usePipelineFormStore((s) => s.removeAtlas);
  const addAtlas = usePipelineFormStore((s) => s.addAtlas);
  const order = ['subcortical_volume', 'cortical_volume', 'cortical_thickness'];

  const [atlasPickerStatKey, setAtlasPickerStatKey] = React.useState<string | null>(null);
  const [atlasSearch, setAtlasSearch] = React.useState('');

  const removeAtlas = (statKey: string, atlasKey: string) =>
    removeAtlasStore(statKey, atlasKey, metadata as Record<string, unknown>);

  return (
    <Panel
      icon={
        <span className="flex h-5 w-5 items-center">
          <BarChartIcon />
        </span>
      }
      title="Stats & Atlas Mapping"
      className="min-w-0"
    >
      <div id="statsAtlasGroups" className="divide-y divide-cursor-hairline-soft">
        {order.map((statKey) => {
          const stat = metadata?.stats_vectors?.[statKey];
          const selectedAtlases = selectedStatsAtlases[statKey] || [];
          const atlasKeys = Array.isArray(stat?.atlases) ? stat.atlases : [];

          return (
            <div key={statKey} className="py-4 first:pt-0 last:pb-0">
              <div className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-2.5">
                <span className="flex min-h-8 items-center gap-2 text-[12px] font-semibold uppercase text-cursor-ink">
                  <span className="h-2 w-2 shrink-0 rounded-full bg-cursor-primary" />
                  {(stat?.label || statKey).toUpperCase()}
                </span>

                <button
                  type="button"
                  onClick={() => {
                    setAtlasPickerStatKey(statKey);
                    setAtlasSearch('');
                  }}
                  className="inline-flex h-10 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-cursor-hairline bg-white px-4 text-sm font-semibold text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft"
                >
                  + Add Atlas
                </button>

                <div className="col-span-2 flex flex-wrap gap-2 pl-4">
                {selectedAtlases.length ? (
                  selectedAtlases.map((atlasKey) => {
                    const atlas = metadata?.atlases?.[atlasKey] || {key: atlasKey, label: atlasKey};
                    return (
                      <span
                        key={atlasKey}
                        className="inline-flex items-center gap-2 rounded-lg border border-cursor-hairline bg-white py-1.5 pl-3 pr-2 text-sm font-medium text-cursor-ink"
                      >
                        {atlas.label || atlas.key}
                        <button
                          type="button"
                          onClick={() => removeAtlas(statKey, atlas.key)}
                          className="flex h-5 w-5 items-center justify-center rounded hover:bg-cursor-canvas-soft text-cursor-muted hover:text-cursor-semantic-error font-bold text-[11px]"
                          title="Remove atlas"
                        >
                          ✕
                        </button>
                      </span>
                    );
                  })
                ) : (
                  <span className="text-[12px] italic text-cursor-muted">No atlases mapped to this statistic.</span>
                )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {atlasPickerStatKey && (() => {
        const pickerStat = metadata?.stats_vectors?.[atlasPickerStatKey];
        const pickerAtlasKeys = Array.isArray(pickerStat?.atlases) ? pickerStat.atlases : [];
        const pickerSelectedAtlases = selectedStatsAtlases[atlasPickerStatKey] || [];
        const pickerLabel = pickerStat?.label || atlasPickerStatKey;
        const filteredAtlasKeys = pickerAtlasKeys.filter((atlasKey) => {
          const atlas = metadata?.atlases?.[atlasKey] || {key: atlasKey, label: atlasKey};
          const query = atlasSearch.trim().toLowerCase();
          if (!query) return true;
          return `${atlas.label || ''} ${atlas.key || atlasKey}`.toLowerCase().includes(query);
        });

        return (
          <ModalOverlay onClose={() => { setAtlasPickerStatKey(null); setAtlasSearch(''); }}>
            <div role="dialog" aria-modal="true" aria-labelledby="atlas-picker-title">
              <h3 id="atlas-picker-title" className="m-0 mb-4 text-[16px] font-semibold leading-[1.4] text-cursor-ink">
                Add Atlas to {pickerLabel.toUpperCase()}
              </h3>
              <input
                type="text"
                value={atlasSearch}
                onChange={(e) => setAtlasSearch(e.target.value)}
                placeholder="Search atlases…"
                autoFocus
                className={`${inputCls} mb-3`}
              />
              <div className="max-h-[min(34rem,calc(100vh-6rem))] space-y-1.5 overflow-y-auto pr-1">
                {filteredAtlasKeys.length ? (
                  filteredAtlasKeys.map((atlasKey) => {
                    const atlas = metadata?.atlases?.[atlasKey] || {key: atlasKey, label: atlasKey};
                    const isSelected = pickerSelectedAtlases.includes(atlasKey);
                    return (
                      <button
                        key={atlasKey}
                        type="button"
                        disabled={isSelected}
                        onClick={() => addAtlas(atlasPickerStatKey, atlasKey)}
                        className={`flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                          isSelected
                            ? 'cursor-default border-cursor-hairline bg-cursor-canvas-soft text-cursor-muted'
                            : 'cursor-pointer border-cursor-hairline bg-white text-cursor-ink hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft'
                        }`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-semibold">{atlas.label || atlas.key}</span>
                          <span className="block truncate text-[12px] text-cursor-muted">{atlas.key}</span>
                        </span>
                        {isSelected ? <span className="shrink-0 rounded-full bg-cursor-hairline px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-body">Selected</span> : null}
                      </button>
                    );
                  })
                ) : (
                  <p className="py-6 text-center text-sm italic text-cursor-muted">No atlases match this search.</p>
                )}
              </div>
              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={() => { setAtlasPickerStatKey(null); setAtlasSearch(''); }}
                  className="inline-flex h-9 items-center justify-center rounded-lg border border-cursor-hairline bg-white px-4 text-sm font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft"
                >
                  Close
                </button>
              </div>
            </div>
          </ModalOverlay>
        );
      })()}
    </Panel>
  );
}

export function AdvancedSettingsSection() {
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);
  const neuroflowEnabled = Boolean(formValues.neuroflowEnabled);

  return (
    <Panel
      icon={<SlidersHorizontal className="h-5 w-5 text-cursor-primary" />}
      title="Advanced Settings"
      className="min-w-0"
    >
      <div className="grid gap-4">
        <label className="flex cursor-pointer items-center gap-3">
          <input
            type="checkbox"
            checked={neuroflowEnabled}
            onChange={(e) => setFormField('neuroflowEnabled', e.target.checked)}
            className="h-4 w-4 accent-cursor-primary"
          />
          <span className="text-base font-medium text-cursor-ink">Enable NeuroFLOW scheduler</span>
        </label>
        <p className="text-sm text-cursor-muted -mt-2 pl-7">
          Use NeuroFLOW to schedule supported preset pipeline runs across images and stages.
        </p>

        {neuroflowEnabled && (
          <>
            <label className={labelCls}>
              Max concurrent tasks
              <input
                type="number"
                min={1}
                step={1}
                value={formValues.neuroflowMaxConcurrentTasks ?? 1}
                onChange={(e) => setFormField('neuroflowMaxConcurrentTasks', Math.max(1, parseInt(e.target.value, 10) || 1))}
                className={inputCls}
              />
              <span className="text-[11px] text-cursor-muted mt-1">
                Maximum scheduler launches to execute at the same time.
              </span>
            </label>

            <label className={labelCls}>
              Machine profile
              <input
                type="text"
                value={formValues.neuroflowMachineProfileId ?? 'application_default'}
                disabled
                className={`${inputCls} opacity-70 cursor-not-allowed`}
              />
              <span className="text-[11px] text-cursor-muted mt-1">
                Currently fixed to application_default.
              </span>
            </label>
          </>
        )}
      </div>
    </Panel>
  );
}

function BarChartIcon() {
  return (
    <svg
      className="h-5 w-5 text-cursor-primary"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 3v18h18" />
      <path d="M18 17V9" />
      <path d="M13 17V5" />
      <path d="M8 17v-3" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Shared small components for Input & Output section
// ---------------------------------------------------------------------------

function ModalOverlay({onClose, children}: {onClose: () => void; children: React.ReactNode}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-[min(42rem,calc(100vw-2rem))] rounded-xl border border-cursor-hairline bg-white p-6 shadow-none">
        {children}
      </div>
    </div>
  );
}

function ModalTitle({children}: {children: React.ReactNode}) {
  return <h3 className="m-0 mb-4 text-[16px] font-semibold leading-[1.4] text-cursor-ink">{children}</h3>;
}

function remoteBrowseErrorMessage(message: string | undefined): string {
  if (message === 'Not found') {
    return 'Remote browse endpoint is not available. Restart npm run dev so the backend loads the latest code.';
  }
  return message || 'Browse failed.';
}

// ---------------------------------------------------------------------------
// formatBytes helper
// ---------------------------------------------------------------------------

function fmtBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// ServerBrowserModal — real SFTP directory browser when SSH is connected
// ---------------------------------------------------------------------------

// ModalOverlay for wide modals (browser popup)
function WideModalOverlay({onClose, children}: {onClose: () => void; children: React.ReactNode}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-cursor-ink/30 p-6"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative my-auto w-full max-w-[min(56rem,calc(100vw-3rem))] rounded-xl border border-cursor-hairline bg-white shadow-none">
        {children}
      </div>
    </div>
  );
}

function ServerBrowserModal({
  title,
  initialPath,
  remotePayload,
  selectMode,
  onConfirm,
  onClose,
  onSelectFiles,
}: {
  title: string;
  initialPath: string;
  remotePayload: Record<string, unknown>;
  selectMode: 'path' | 'files';
  onConfirm: (path: string) => void;
  onClose: () => void;
  onSelectFiles?: (paths: string[], count: number) => void;
}) {
  const browseMutation = useRemoteBrowseMutation();
  const [currentPath, setCurrentPath] = React.useState(initialPath || '~');
  const [entries, setEntries] = React.useState<RemoteBrowseEntry[]>([]);
  const [parentPath, setParentPath] = React.useState('~');
  const [selectedFiles, setSelectedFiles] = React.useState<Set<string>>(new Set());
  const [statusMsg, setStatusMsg] = React.useState('');
  const [isError, setIsError] = React.useState(false);
  const [manualPath, setManualPath] = React.useState(initialPath || '');

  const doBrowse = React.useCallback(
    (path: string) => {
      setStatusMsg('Loading...');
      setIsError(false);
      browseMutation.mutate(
        {...remotePayload, path} as Parameters<typeof browseMutation.mutate>[0],
        {
          onSuccess: (res) => {
            if (!res.ok) {
              setStatusMsg(remoteBrowseErrorMessage(res.error));
              setIsError(true);
              setEntries([]);
              return;
            }
            setCurrentPath(res.path ?? path);
            setManualPath(res.path ?? path);
            setParentPath(res.parent ?? res.path ?? path);
            setEntries(res.entries ?? []);
            setStatusMsg('');
            setIsError(false);
          },
          onError: (err: unknown) => {
            setStatusMsg(remoteBrowseErrorMessage((err as Error).message));
            setIsError(true);
          },
        },
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [remotePayload],
  );

  React.useEffect(() => {
    doBrowse(initialPath || '~');
    // only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleFile = (path: string) => {
    setSelectedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const dirs = entries.filter((e) => e.kind === 'directory');
  const files = entries.filter((e) => e.kind === 'file');
  const isLoading = browseMutation.isPending;

  return (
    <WideModalOverlay onClose={onClose}>
      {/* Header */}
      <div className="border-b border-cursor-hairline px-6 py-4">
        <h3 className="m-0 text-[15px] font-semibold text-cursor-ink">{title}</h3>
        {/* Path bar */}
        <div className="mt-3 flex gap-2">
          <input
            className={`${inputCls} min-w-0 flex-1 font-mono text-[12px]`}
            value={manualPath}
            onChange={(e) => setManualPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') doBrowse(manualPath);
            }}
            placeholder="/home/user/mri-data"
            aria-label="Remote path"
          />
          <button
            type="button"
            onClick={() => doBrowse(manualPath)}
            disabled={isLoading}
            className="inline-flex h-11 flex-none cursor-pointer items-center justify-center rounded-lg border border-cursor-hairline bg-white px-4 text-sm font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-50"
          >
            Go
          </button>
        </div>
      </div>

      {/* Entry list */}
      <div className="max-h-[min(28rem,60vh)] overflow-y-auto bg-cursor-canvas-soft">
        {/* Up row */}
        {parentPath !== currentPath && !isLoading && (
          <button
            type="button"
            onClick={() => doBrowse(parentPath)}
            className="flex w-full items-center gap-3 border-b border-cursor-hairline-soft px-6 py-2.5 text-left text-[12px] text-cursor-primary hover:bg-white"
          >
            <span className="inline-flex h-5 w-8 flex-none items-center justify-center rounded text-[10px] font-semibold uppercase tracking-wide text-cursor-muted">
              UP
            </span>
            <span className="min-w-0 flex-1 truncate font-mono">..</span>
          </button>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-10 text-[12px] text-cursor-muted">Loading...</div>
        )}

        {/* Error */}
        {!isLoading && isError && statusMsg && (
          <div className="px-6 py-4 text-[12px] text-cursor-semantic-error">{statusMsg}</div>
        )}

        {/* Empty */}
        {!isLoading && !isError && entries.length === 0 && (
          <div className="flex items-center justify-center py-10 text-[12px] text-cursor-muted">
            Empty directory.
          </div>
        )}

        {/* Directories */}
        {!isLoading &&
          dirs.map((entry) => (
            <button
              key={entry.path}
              type="button"
              title={entry.path}
              onClick={() => {
                if (selectMode === 'path') setManualPath(entry.path);
                doBrowse(entry.path);
              }}
              className="flex w-full items-center gap-3 border-b border-cursor-hairline-soft px-6 py-2.5 text-left text-[12px] hover:bg-white"
            >
              <span className="inline-flex h-5 w-8 flex-none items-center justify-center rounded bg-cursor-primary/10 text-[10px] font-semibold uppercase tracking-wide text-cursor-primary">
                DIR
              </span>
              <span className="min-w-0 flex-1 truncate font-medium text-cursor-ink">{entry.name}</span>
            </button>
          ))}

        {/* Files */}
        {!isLoading &&
          files.map((entry) => {
            const checked = selectedFiles.has(entry.path);
            const isImg = entry.selectable;
            const badge = isImg ? 'IMG' : 'FILE';
            const badgeCls = isImg
              ? 'bg-cursor-primary/8 text-cursor-primary'
              : 'bg-cursor-canvas text-cursor-muted';
            return (
              <div
                key={entry.path}
                className="flex w-full items-center gap-3 border-b border-cursor-hairline-soft px-6 py-2.5 text-[12px]"
              >
                {selectMode === 'files' && isImg && (
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleFile(entry.path)}
                    className="h-3.5 w-3.5 flex-none accent-cursor-primary"
                  />
                )}
                {!(selectMode === 'files' && isImg) && <span className="h-3.5 w-3.5 flex-none" />}
                <span
                  className={`inline-flex h-5 w-8 flex-none items-center justify-center rounded text-[10px] font-semibold uppercase tracking-wide ${badgeCls}`}
                >
                  {badge}
                </span>
                <button
                  type="button"
                  title={entry.path}
                  onClick={() => {
                    if (selectMode === 'path') setManualPath(entry.path);
                    else if (isImg) toggleFile(entry.path);
                  }}
                  className={`min-w-0 flex-1 truncate text-left font-mono ${isImg ? 'text-cursor-ink hover:underline' : 'cursor-default text-cursor-muted'}`}
                >
                  {entry.name}
                </button>
                {entry.size != null && (
                  <span className="flex-none text-right text-cursor-muted" style={{minWidth: '4rem'}}>
                    {fmtBytes(entry.size)}
                  </span>
                )}
              </div>
            );
          })}
      </div>

      {/* Sticky footer */}
      <div className="flex items-center justify-between gap-3 border-t border-cursor-hairline px-6 py-4">
        {selectMode === 'files' ? (
          <span className="text-[12px] text-cursor-muted">{selectedFiles.size} file(s) selected</span>
        ) : (
          <span className="min-w-0 truncate font-mono text-[11px] text-cursor-muted" title={manualPath || currentPath}>
            {manualPath || currentPath}
          </span>
        )}
        <div className="flex flex-none gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {selectMode === 'path' ? (
            <Button variant="primary" onClick={() => onConfirm(manualPath || currentPath)}>
              Select path
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={() => {
                if (onSelectFiles) {
                  const arr = Array.from(selectedFiles);
                  onSelectFiles(arr, arr.length);
                }
                onClose();
              }}
            >
              Confirm ({selectedFiles.size})
            </Button>
          )}
        </div>
      </div>
    </WideModalOverlay>
  );
}

// ---------------------------------------------------------------------------
// Batch Configure Modal — recursive scan with depth controls
// ---------------------------------------------------------------------------

type ScanMode = 'direct' | 'one-level' | 'recursive';

type BatchScanCache = {
  cacheKey: string;
  scanMode: ScanMode;
  entries: RemoteBrowseEntry[];
  selectedPaths: string[];
  status: string;
  hasConflict: boolean;
  subjectCount: number;
  scanned: boolean;
};

const SCAN_MODE_OPTIONS: {value: ScanMode; label: string; hint: string; maxDepth: number}[] = [
  {value: 'direct', label: 'Direct files only', hint: 'Image files immediately in the input folder.', maxDepth: 0},
  {
    value: 'one-level',
    label: 'One level of subfolders',
    hint: 'ADNI-style: one scan file per subject subfolder.',
    maxDepth: 1,
  },
  {value: 'recursive', label: 'Recursive', hint: 'Scan up to 6 levels deep.', maxDepth: 6},
];

function BatchConfigModal({
  inputSource,
  inputPath,
  currentCount,
  onConfirm,
  onClose,
  localFileListLen,
  isConnected,
  remotePayload,
  cacheKey,
  batchScanCache,
  setBatchScanCache,
}: {
  inputSource: string;
  inputPath: string;
  currentCount: number | undefined;
  onConfirm: (count: number, paths?: string[]) => void;
  onClose: () => void;
  localFileListLen: number;
  isConnected: boolean;
  remotePayload: Record<string, unknown>;
  cacheKey: string;
  batchScanCache: BatchScanCache | null;
  setBatchScanCache: React.Dispatch<React.SetStateAction<BatchScanCache | null>>;
}) {
  const remoteBrowseMutation = useRemoteBrowseMutation();
  const localBrowseMutation = useLocalBrowseMutation();
  const [count, setCount] = React.useState<number>(currentCount ?? (localFileListLen || 1));

  const isServer = inputSource === 'Server';
  const canScan = isServer ? isConnected : !!inputPath;
  const scanPending = isServer ? remoteBrowseMutation.isPending : localBrowseMutation.isPending;
  const cacheMatches = batchScanCache?.cacheKey === cacheKey && batchScanCache?.scanned;

  const [serverEntries, setServerEntries] = React.useState<RemoteBrowseEntry[]>(
    cacheMatches ? batchScanCache!.entries : [],
  );
  const [selectedPaths, setSelectedPaths] = React.useState<Set<string>>(
    cacheMatches ? new Set(batchScanCache!.selectedPaths) : new Set(),
  );
  const [scanStatus, setScanStatus] = React.useState(cacheMatches ? batchScanCache!.status : '');
  const [scanMode, setScanMode] = React.useState<ScanMode>(cacheMatches ? batchScanCache!.scanMode : 'one-level');
  const [scanned, setScanned] = React.useState(cacheMatches ? batchScanCache!.scanned : false);
  const [hasConflict, setHasConflict] = React.useState(cacheMatches ? batchScanCache!.hasConflict : false);

  const doScan = React.useCallback(
    (mode: ScanMode, force = false) => {
      if (!inputPath) {
        setScanStatus('Set an input location first.');
        return;
      }
      if (!force && batchScanCache?.cacheKey === cacheKey && batchScanCache?.scanned && batchScanCache?.scanMode === mode) {
        return;
      }
      const modeOpt = SCAN_MODE_OPTIONS.find((o) => o.value === mode)!;
      setScanStatus('Scanning...');
      setServerEntries([]);
      setSelectedPaths(new Set());
      setScanned(false);

      const handleSuccess = (res: RemoteBrowseResponse) => {
        if (!res.ok) {
          setScanStatus(remoteBrowseErrorMessage(res.error));
          return;
        }
        const candidates = (res.entries ?? []).filter((e) => e.kind === 'file' && e.selectable);
        setServerEntries(candidates);
        setHasConflict(res.has_multi_subject_conflict ?? false);

        // Auto-select: all candidates whose subject_label is unique (exactly 1 image per folder)
        const labelCounts = new Map<string, number>();
        for (const e of candidates) {
          const lbl = e.subject_label ?? e.name;
          labelCounts.set(lbl, (labelCounts.get(lbl) ?? 0) + 1);
        }
        const autoSelected = new Set<string>();
        for (const e of candidates) {
          const lbl = e.subject_label ?? e.name;
          if ((labelCounts.get(lbl) ?? 0) === 1) {
            autoSelected.add(e.path);
          }
        }
        setSelectedPaths(autoSelected);
        setCount(autoSelected.size || candidates.length || 1);
        const statusText = candidates.length === 0
          ? 'No image files found in this directory.'
          : `${candidates.length} image${candidates.length !== 1 ? 's' : ''} found across ${labelCounts.size} subject${labelCounts.size !== 1 ? 's' : ''}.`;
        setScanStatus(statusText);
        setScanned(true);
        setBatchScanCache({
          cacheKey,
          scanMode: mode,
          entries: candidates,
          selectedPaths: Array.from(autoSelected),
          status: statusText,
          hasConflict: res.has_multi_subject_conflict ?? false,
          subjectCount: labelCounts.size,
          scanned: true,
        });
      };

      if (isServer) {
        remoteBrowseMutation.mutate(
          {
            ...remotePayload,
            path: inputPath,
            purpose: 'batch',
            recursive: true,
            max_depth: modeOpt.maxDepth,
          } as Parameters<typeof remoteBrowseMutation.mutate>[0],
          {
            onSuccess: handleSuccess,
            onError: (err: unknown) => setScanStatus(remoteBrowseErrorMessage((err as Error).message)),
          },
        );
      } else {
        localBrowseMutation.mutate(
          {path: inputPath, max_depth: modeOpt.maxDepth},
          {
            onSuccess: handleSuccess,
            onError: (err: unknown) => setScanStatus(remoteBrowseErrorMessage((err as Error).message)),
          },
        );
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isServer, remoteBrowseMutation, localBrowseMutation, remotePayload, inputPath, cacheKey, batchScanCache],
  );

  // Hydrate from cache or scan on first open
  React.useEffect(() => {
    if (canScan && inputPath && !cacheMatches) {
      doScan(scanMode, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const togglePath = (path: string) => {
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const finalCount = scanned ? selectedPaths.size : (selectedPaths.size > 0 ? selectedPaths.size : count);

  return (
    <WideModalOverlay onClose={onClose}>
      {/* Header */}
      <div className="border-b border-cursor-hairline px-6 py-4">
        <h3 className="m-0 text-[15px] font-semibold text-cursor-ink">Configure Batch Settings</h3>
        <p className="mt-1 text-[12px] text-cursor-muted">
          {isServer && !isConnected
            ? 'Connect to the server first to scan the directory.'
            : `Input path: ${inputPath || '(not set)'}`}
        </p>
      </div>

      {/* Scan controls */}
      {canScan && (
        <div className="border-b border-cursor-hairline px-6 py-4">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[12px] font-medium text-cursor-body">Scan mode</p>
            <button
              type="button"
              onClick={() => doScan(scanMode, true)}
              disabled={scanPending}
              className="rounded-lg border border-cursor-hairline bg-white px-3 py-1.5 text-[12px] font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              Re-scan
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {SCAN_MODE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  setScanMode(opt.value);
                  doScan(opt.value);
                }}
                title={opt.hint}
                className={`rounded-lg border px-3 py-1.5 text-[12px] font-medium transition-colors ${
                  scanMode === opt.value
                    ? 'border-cursor-primary bg-cursor-primary text-white'
                    : 'border-cursor-hairline bg-white text-cursor-ink hover:border-cursor-hairline-strong'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {scanStatus && (
            <p className={`mt-2 text-[12px] ${hasConflict ? 'text-cursor-semantic-error' : 'text-cursor-muted'}`}>
              {scanStatus}
              {hasConflict && ' Multiple images found for some subjects - review selections below.'}
            </p>
          )}
        </div>
      )}

      {/* Candidate list */}
      {canScan && serverEntries.length > 0 && (
        <TooltipProvider>
          <div className="max-h-[min(24rem,55vh)] overflow-y-auto bg-cursor-canvas-soft">
            {/* Table header */}
          <div className="grid border-b border-cursor-hairline px-6 py-2 text-[11px] font-semibold uppercase tracking-wide text-cursor-muted" style={{gridTemplateColumns: '1.5rem minmax(10rem,1.8fr) minmax(4.5rem,0.7fr) minmax(14rem,3fr) 4.5rem'}}>
            <span />
            <span>Subject</span>
            <span>Filename</span>
            <span className="hidden sm:block">Relative path</span>
            <span className="text-right">Size</span>
          </div>
          {serverEntries.map((entry) => {
            const checked = selectedPaths.has(entry.path);
            return (
              <div
                key={entry.path}
                role="button"
                tabIndex={0}
                onClick={() => togglePath(entry.path)}
                onKeyDown={(e) => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); togglePath(entry.path); } }}
                className="grid cursor-pointer items-center border-b border-cursor-hairline-soft px-6 py-2 hover:bg-white"
                style={{gridTemplateColumns: '1.5rem minmax(10rem,1.8fr) minmax(4.5rem,0.7fr) minmax(14rem,3fr) 4.5rem'}}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  readOnly
                  className="h-3.5 w-3.5 accent-cursor-primary pointer-events-none"
                />
                <Tooltip>
                  <TooltipTrigger className="min-w-0 w-full text-left">
                    <span className="block min-w-0 truncate pr-2 text-[12px] font-medium text-cursor-ink">
                      {entry.subject_label ?? '-'}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" align="start" className="max-w-md break-all">
                    {entry.subject_label ?? '-'}
                  </TooltipContent>
                </Tooltip>
                <span className="min-w-0 truncate pr-2 font-mono text-[12px] text-cursor-ink">
                  {entry.name}
                </span>
                <Tooltip>
                  <TooltipTrigger className="hidden min-w-0 w-full text-left sm:block">
                    <span className="block min-w-0 truncate pr-2 font-mono text-[11px] text-cursor-muted">
                      {entry.relative_path ?? ''}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" align="start" className="max-w-md break-all">
                    {entry.relative_path ?? entry.path}
                  </TooltipContent>
                </Tooltip>
                <span className="text-right text-[11px] text-cursor-muted">{fmtBytes(entry.size)}</span>
              </div>
            );
          })}
          </div>
        </TooltipProvider>
      )}

      {/* Manual count fallback (local or not yet scanned) */}
      <div className="px-6 py-4">
        {(!canScan || !scanned) && (
          <label className={labelCls}>
            Number of images to process
            <input
              type="number"
              min={1}
              step={1}
              className={inputCls}
              value={count}
              onChange={(e) => {
                setCount(Math.max(1, parseInt(e.target.value, 10) || 1));
                setSelectedPaths(new Set());
              }}
            />
          </label>
        )}
        {canScan && scanned && (
          <div className="flex items-center justify-between gap-3">
            <p className="text-[12px] text-cursor-muted">{selectedPaths.size} selected</p>
            <div className="flex gap-2">
              {selectedPaths.size !== serverEntries.length && (
                <button
                  type="button"
                  onClick={() => setSelectedPaths(new Set(serverEntries.map((e) => e.path)))}
                  className="text-[12px] text-cursor-primary hover:underline"
                >
                  Select all
                </button>
              )}
              {selectedPaths.size > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedPaths(new Set())}
                  className="text-[12px] text-cursor-primary hover:underline"
                >
                  Unselect all
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex justify-end gap-2 border-t border-cursor-hairline px-6 py-4">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="primary"
          disabled={canScan && scanned && selectedPaths.size === 0}
          onClick={() => {
            const paths = scanned && selectedPaths.size > 0 ? Array.from(selectedPaths) : undefined;
            onConfirm(finalCount, paths);
          }}
        >
          Save selection
        </Button>
      </div>
    </WideModalOverlay>
  );
}

// ---------------------------------------------------------------------------
// PathField — input + browse button row
// ---------------------------------------------------------------------------

function PathField({
  id,
  label,
  value,
  placeholder,
  onChange,
  onBrowse,
  required,
}: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  onChange: (v: string) => void;
  onBrowse: () => void;
  required?: boolean;
}) {
  return (
    <label className={labelCls}>
      {label}
      <div className="flex gap-2">
        <input
          id={id}
          name={id}
          value={value}
          placeholder={placeholder}
          required={required}
          onChange={(e) => onChange(e.target.value)}
          className={`${inputCls} flex-1`}
        />
        <button
          type="button"
          onClick={onBrowse}
          title="Browse"
          className="inline-flex h-11 flex-none cursor-pointer items-center justify-center rounded-lg border border-cursor-hairline bg-white px-3 text-sm font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft"
        >
          Browse
        </button>
      </div>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Radio group helper
// ---------------------------------------------------------------------------

function RadioGroup({
  name,
  options,
  value,
  onChange,
  disabled,
}: {
  name: string;
  options: {label: string; value: string; hint?: string}[];
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      {options.map((opt) => (
        <label
          key={opt.value}
          className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-3.5 py-2.5 transition-colors ${
            value === opt.value
              ? 'border-cursor-primary bg-cursor-canvas-soft'
              : 'border-cursor-hairline bg-white hover:border-cursor-hairline-strong'
          } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
        >
          <input
            type="radio"
            name={name}
            value={opt.value}
            checked={value === opt.value}
            disabled={disabled}
            onChange={() => !disabled && onChange(opt.value)}
            className="mt-0.5 h-4 w-4 flex-none accent-cursor-primary"
          />
          <span className="grid gap-0.5">
            <span className="text-[13px] font-medium leading-[1.4] text-cursor-ink">{opt.label}</span>
            {opt.hint && <span className="text-[12px] leading-[1.4] text-cursor-muted">{opt.hint}</span>}
          </span>
        </label>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// InputOutputSection — main export
// ---------------------------------------------------------------------------

export function InputOutputSection() {
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);
  const setFormFields = usePipelineFormStore((s) => s.setFormFields);

  // Remote connection state
  const remoteConnected = useRemoteStore((s) => s.connected);
  const remotePayload = buildRemotePayload(formValues) as unknown as Record<string, unknown>;

  // Derived helpers
  const isLocal = formValues.runtimeTarget === 'Local';
  const inputSource = formValues.inputSource as string;
  const isBatch = formValues.inputMode === 'batch_folder';
  const isServerSource = inputSource === 'Server';

  // Modal states
  const [serverInputModal, setServerInputModal] = React.useState(false);
  const [serverOutputModal, setServerOutputModal] = React.useState(false);
  const [batchModal, setBatchModal] = React.useState(false);
  const [uploadNotice, setUploadNotice] = React.useState(false);

  // Batch scan cache — persists across modal open/close
  const [batchScanCache, setBatchScanCache] = React.useState<BatchScanCache | null>(null);
  const batchCacheKey = `${inputSource}|${formValues.inputPath}|${JSON.stringify(remotePayload)}`;

  // Invalidate cache when inputs change
  React.useEffect(() => {
    setBatchScanCache((prev) => (prev && prev.cacheKey !== batchCacheKey ? null : prev));
  }, [batchCacheKey]);

  // Ref for hidden local file input (browser fallback for directory browse)
  const localInputRef = React.useRef<HTMLInputElement | null>(null);
  const [localFileListLen, setLocalFileListLen] = React.useState(0);

  // When runtime is Local, force source to Local
  React.useEffect(() => {
    if (isLocal && inputSource === 'Server') {
      setFormField('inputSource', 'Local');
    }
  }, [isLocal, inputSource, setFormField]);

  // Input Mode radio options — map to existing backend inputMode values
  const inputModeOptions = [
    {label: 'Single input', value: 'file', hint: 'Process one NIfTI or DICOM file.'},
    {label: 'Batch input', value: 'batch_folder', hint: 'Process a folder of images.'},
  ];

  // Source radio options
  const sourceOptions = [
    {label: 'Local', value: 'Local', hint: 'Files on this machine.'},
    {label: 'Server', value: 'Server', hint: 'Files on the remote server.'},
  ];

  const handleLocalBrowseInput = async () => {
    if (isBatch) {
      if (!hasTauriInternals()) {
        alert('Folder picker is not available in browser mode. Please type the folder path manually.');
        return;
      }
      try {
        const selected = await open({directory: true, multiple: false});
        if (selected) {
          setFormField('inputPath', selected);
        }
      } catch {
        // dialog cancelled or unavailable
      }
    } else {
      localInputRef.current?.click();
    }
  };

  const handleLocalFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    if (files.length === 1 && files[0]) {
      setFormField('inputPath', files[0].name);
    }
    setLocalFileListLen(files.length);
  };

  // Upload to server — intentionally no-op
  const handleUploadToServer = () => {
    setUploadNotice(true);
    setTimeout(() => setUploadNotice(false), 3500);
  };

  return (
    <>
      <Panel icon={<FolderInput className="h-5 w-5 text-cursor-primary" />} title="Input & Output" className="min-w-0">
        <div className="grid gap-6">
          {/* Row 1: Source + Input Mode */}
          <div className="grid gap-6 grid-cols-2 max-[1080px]:grid-cols-1 items-start">
            {/* Source */}
            <div className="grid gap-3">
              <span className="text-[13px] font-normal leading-[1.4] text-cursor-body">Source Input</span>
              <RadioGroup
                name="inputSource"
                options={sourceOptions}
                value={inputSource}
                onChange={(v) => setFormField('inputSource', v)}
                disabled={isLocal}
              />
              {isLocal && (
                <p className="text-[11px] leading-[1.4] text-cursor-muted">
                  Server source is unavailable when Runtime Target is Local.
                </p>
              )}
              {isServerSource && remoteConnected && (
                <div className="flex items-center gap-3">
                  <Button variant="ghost" icon={<Upload className="h-4 w-4" />} onClick={handleUploadToServer}>
                    Upload data to server
                  </Button>
                  {uploadNotice && (
                    <span className="text-[12px] text-cursor-muted">Not wired yet - upload feature coming soon.</span>
                  )}
                </div>
              )}
            </div>

            {/* Input Mode */}
            <div className="grid gap-3">
              <span className="text-[13px] font-normal leading-[1.4] text-cursor-body">Input Mode</span>
              <RadioGroup
                name="inputMode"
                options={inputModeOptions}
                value={isBatch ? 'batch_folder' : 'file'}
                onChange={(v) => setFormField('inputMode', v)}
              />
              {isBatch && (
                <div className="flex items-center gap-3">
                  <Button variant="ghost" icon={<SlidersHorizontal className="h-4 w-4" />} onClick={() => setBatchModal(true)}>
                    Configure batch
                  </Button>
                  {formValues.batchImageCount !== undefined && (
                    <span className="text-[12px] text-cursor-muted">{formValues.batchImageCount} selected</span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-cursor-hairline-soft" />

          {/* Server not-connected notice */}
          {isServerSource && !remoteConnected && (
            <div className="rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-3">
              <p className="text-[13px] font-medium text-cursor-ink">SSH not connected</p>
              <p className="mt-0.5 text-[12px] text-cursor-muted">
                Connect in the SSH Server card below to enable server browsing.
              </p>
            </div>
          )}

          {/* Row 2: Path fields — Local */}
          {inputSource === 'Local' && (
            <div className="grid gap-4">
              <PathField
                id="inputPath"
                label="Input location"
                value={formValues.inputPath}
                placeholder="/data/sub-001_T1w.nii.gz or /data/batch"
                onChange={(v) => setFormField('inputPath', v)}
                onBrowse={handleLocalBrowseInput}
                required
              />
              {/* Hidden file input — browser-safe fallback */}
              <input
                ref={localInputRef}
                className="hidden"
                type="file"
                multiple
                onChange={handleLocalFileChange}
              />
              <PathField
                id="outputDir"
                label="Output location"
                value={formValues.outputDir}
                placeholder="/outputs/project"
                onChange={(v) => setFormField('outputDir', v)}
                onBrowse={() => {
                  alert('Directory picker is not available in browser mode. Please type the path manually.');
                }}
                required
              />
            </div>
          )}

          {/* Row 2: Path fields — Server */}
          {inputSource === 'Server' && (
            <div className="grid gap-4">
              <PathField
                id="inputPath"
                label="Input location (server path)"
                value={formValues.inputPath}
                placeholder="/home/user/mri-data"
                onChange={(v) => setFormField('inputPath', v)}
                onBrowse={() => setServerInputModal(true)}
                required
              />
              <PathField
                id="outputDir"
                label="Output location (server path)"
                value={formValues.outputDir}
                placeholder="/home/user/mri-outputs"
                onChange={(v) => setFormField('outputDir', v)}
                onBrowse={() => setServerOutputModal(true)}
                required
              />
            </div>
          )}

        </div>
      </Panel>

      {/* Server input browse modal */}
      {serverInputModal && (
        remoteConnected ? (
          <ServerBrowserModal
            title="Browse server - Input location"
            initialPath={formValues.inputPath || '~'}
            remotePayload={remotePayload}
            selectMode="path"
            onConfirm={(p) => {
              setFormField('inputPath', p);
              setServerInputModal(false);
            }}
            onClose={() => setServerInputModal(false)}
          />
        ) : (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30"
            onMouseDown={() => setServerInputModal(false)}
          >
            <div className="rounded-xl border border-cursor-hairline bg-white p-6 max-w-sm w-full">
              <h3 className="m-0 mb-3 text-[16px] font-semibold text-cursor-ink">SSH not connected</h3>
              <p className="text-[13px] text-cursor-muted">Connect in the SSH Server card first, then browse.</p>
              <div className="mt-4 flex justify-end">
                <Button variant="ghost" onClick={() => setServerInputModal(false)}>Close</Button>
              </div>
            </div>
          </div>
        )
      )}

      {/* Server output browse modal */}
      {serverOutputModal && (
        remoteConnected ? (
          <ServerBrowserModal
            title="Browse server - Output location"
            initialPath={formValues.outputDir || '~'}
            remotePayload={remotePayload}
            selectMode="path"
            onConfirm={(p) => {
              setFormField('outputDir', p);
              setServerOutputModal(false);
            }}
            onClose={() => setServerOutputModal(false)}
          />
        ) : (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30"
            onMouseDown={() => setServerOutputModal(false)}
          >
            <div className="rounded-xl border border-cursor-hairline bg-white p-6 max-w-sm w-full">
              <h3 className="m-0 mb-3 text-[16px] font-semibold text-cursor-ink">SSH not connected</h3>
              <p className="text-[13px] text-cursor-muted">Connect in the SSH Server card first, then browse.</p>
              <div className="mt-4 flex justify-end">
                <Button variant="ghost" onClick={() => setServerOutputModal(false)}>Close</Button>
              </div>
            </div>
          </div>
        )
      )}

      {/* Batch config modal */}
      {batchModal && (
        <BatchConfigModal
          inputSource={inputSource}
          inputPath={formValues.inputPath}
          currentCount={formValues.batchImageCount as number | undefined}
          localFileListLen={localFileListLen}
          isConnected={remoteConnected}
          remotePayload={remotePayload}
          cacheKey={batchCacheKey}
          batchScanCache={batchScanCache}
          setBatchScanCache={setBatchScanCache}
          onConfirm={(n, paths) => {
            // Update cache with final selections before closing
            setBatchScanCache((prev) =>
              prev ? {...prev, selectedPaths: paths && paths.length > 0 ? paths : prev.selectedPaths} : prev,
            );
            const patch: Record<string, unknown> = {batchImageCount: n};
            if (paths && paths.length > 0) {
              patch.additionalInputPaths = paths.join(',');
            }
            setFormFields(patch);
            setBatchModal(false);
          }}
          onClose={() => setBatchModal(false)}
        />
      )}
    </>
  );
}



export function PipelinePage() {
  return (
    <SplitPaneForm
      left={
        <div className="grid min-h-0 h-full content-start gap-6 overflow-y-auto pl-6 pt-6 pb-6 pr-4 [scrollbar-gutter:stable] max-[1080px]:h-auto max-[1080px]:overflow-visible max-[1080px]:px-4 max-[1080px]:py-4">
          <PipelineStepsSection />
          <StatsAtlasSection />
          <AdvancedSettingsSection />
        </div>
      }
      right={
        <div className="grid min-h-0 h-full content-start gap-6 overflow-y-auto pl-4 pt-6 pb-6 pr-6 [scrollbar-gutter:stable] max-[1080px]:h-auto max-[1080px]:overflow-visible max-[1080px]:px-4 max-[1080px]:py-4">
          <InputOutputSection />
          <RuntimeSection />
        </div>
      }
    />
  );
}


import React, {useRef} from 'react';
import {Workflow, FolderInput, FolderOpen, Save, Play, Square, Loader2, FileKey, Upload, SlidersHorizontal, Eye, EyeOff, Layers, Plus, Check, X, Search, BarChart3, Zap, RefreshCw, ChevronDown, ChevronRight, Gauge, HardDrive, Cpu, Info} from 'lucide-react';
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
      icon={<Workflow className="h-4 w-4 text-cursor-primary" />}
      title="Pipeline Steps"
      className="min-w-0"
    >
      <div className="mb-2.5 flex flex-wrap items-end gap-2">
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
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            variant="ghost"
            icon={showTools ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            onClick={() => setShowTools((prev) => !prev)}
          >
            {showTools ? 'Hide Tools' : 'Show Tools'}
          </Button>
          <Button variant="ghost" icon={<FolderOpen className="h-3.5 w-3.5" />} onClick={() => browseJsonFile(presetFileInput)}>
            Load Preset
          </Button>
          <Button
            variant="ghost"
            icon={<Save className="h-3.5 w-3.5" />}
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
        <div className="rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft px-3 py-4 text-center">
          <span className="text-xs text-cursor-muted">Connecting to backend&hellip;</span>
        </div>
      )}
      {metaError && !metaLoading && (
        <div className="rounded-lg border border-cursor-semantic-error/30 bg-cursor-semantic-error/5 px-3 py-3">
          <p className="m-0 text-xs font-medium text-cursor-semantic-error">Backend unavailable</p>
          <p className="mt-1 text-xs text-cursor-muted">
            The MRI pipeline backend is not running. Start the dev server with{' '}
            <code className="rounded bg-cursor-canvas-soft px-1 font-mono text-2xs text-cursor-ink">npm run dev</code>{' '}
            from the <code className="rounded bg-cursor-canvas-soft px-1 font-mono text-2xs text-cursor-ink">tauri-app/</code>{' '}
            directory, which also starts the Python backend on port 8765.
          </p>
        </div>
      )}
      {!metaLoading && !metaError && showTools && (
        <div className="grid border border-cursor-hairline rounded-md overflow-hidden">
          {(metadata?.stages || []).length === 0 && (
            <div className="px-3 py-4 text-center text-xs text-cursor-muted">No pipeline stages found.</div>
          )}
          {(metadata?.stages || []).map((stage) => {
            const tools = metadata?.tools_by_stage?.[stage.id] || [];
            const selectedToolKey = ((formValues as Record<string, unknown>)[`stage_${stage.id}`] as string) || '';
            const isUnavailable = selectedToolKey === '';
            return (
              <div
                key={stage.id}
                className={`grid items-center gap-x-3 gap-y-1.5 border-b border-cursor-hairline-soft px-3 py-1.5 last:border-b-0 grid-cols-[minmax(11rem,0.5fr)_minmax(13rem,1fr)] ${isUnavailable ? 'bg-cursor-canvas-soft/70 border-l-2 border-l-cursor-hairline-strong' : 'bg-cursor-surface-card'}`}
              >
                <div className="flex min-h-8 items-center">
                  <strong className={`font-medium text-xs leading-none ${isUnavailable ? 'text-cursor-muted' : 'text-cursor-ink'}`}>{stage.label}</strong>
                </div>
                <select
                  name={`stage_${stage.id}`}
                  value={selectedToolKey}
                  onChange={(e) => handleStageToolChange(stage.id, e.target.value)}
                  className={`${inputCls} ${isUnavailable ? 'opacity-70' : ''}`}
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
        <div className="mt-2.5 flex flex-wrap items-end gap-2">
          <label className={`${labelCls} min-w-[min(100%,14rem)] flex-1`}>
            FreeSurfer license (license.txt)
            <input
              id="licensePath"
              name="licensePath"
              type="text"
              value={licensePath || ''}
              onChange={(event) => setFormField('licensePath', event.target.value)}
              placeholder="Select or enter path to license.txt"
              className={inputCls}
            />
          </label>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              variant="ghost"
              icon={uploadingLicense ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5" />}
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
            >
              {uploadingLicense ? 'Uploading...' : 'Browse'}
            </Button>
            {licensePath && (
              <Button
                variant="ghost"
                onClick={() => setFormField('licensePath', '')}
              >
                Clear
              </Button>
            )}
          </div>
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
        </div>
      )}
    </Panel>
  );
}

export function StatsAtlasSection() {
  const {data: metadata} = useMetadata();
  const selectedStatsAtlases = usePipelineFormStore((s) => s.selectedStatsAtlases);
  const removeAtlas = usePipelineFormStore((s) => s.removeAtlas);
  const toggleAtlas = usePipelineFormStore((s) => s.toggleAtlas);
  const order = ['subcortical_volume', 'cortical_volume', 'cortical_thickness'];

  const [atlasPickerStatKey, setAtlasPickerStatKey] = React.useState<string | null>(null);
  const [atlasSearch, setAtlasSearch] = React.useState('');

  return (
    <Panel
      icon={
        <span className="flex h-4 w-4 items-center text-cursor-primary">
          <BarChart3 className="h-4 w-4" />
        </span>
      }
      title="Stats & Atlas Mapping"
      className="min-w-0"
    >
      <div id="statsAtlasGroups" className="divide-y divide-cursor-hairline-soft">
        {order.map((statKey) => {
          const stat = metadata?.stats_vectors?.[statKey];
          const selectedAtlases = selectedStatsAtlases[statKey] || [];
          const statLabel =
            stat?.label ||
            statKey
              .split('_')
              .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
              .join(' ');

          return (
            <div key={statKey} className="py-2.5 first:pt-0 last:pb-0">
              <div className="grid grid-cols-[1fr_auto] items-center gap-x-2.5 gap-y-2">
                <div className="flex min-h-7 items-center gap-2">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-cursor-primary" />
                  <span className="text-sm font-semibold text-cursor-ink">
                    {statLabel}
                  </span>
                  <span className="inline-flex items-center justify-center rounded-full bg-cursor-canvas-soft border border-cursor-hairline px-1.5 py-0.25 text-2xs font-semibold text-cursor-body min-w-4">
                    {selectedAtlases.length}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    setAtlasPickerStatKey(statKey);
                    setAtlasSearch('');
                  }}
                  className="inline-flex h-7 shrink-0 cursor-pointer items-center gap-1 rounded-md border border-cursor-hairline bg-cursor-surface-card px-2.5 text-xs font-medium text-cursor-ink transition-colors hover:border-cursor-primary hover:text-cursor-primary hover:bg-cursor-canvas-soft active:scale-[0.98]"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Add Atlas</span>
                </button>

                <div className="col-span-2 flex flex-wrap gap-1.5 pl-3">
                  {selectedAtlases.length ? (
                    selectedAtlases.map((atlasKey) => {
                      const atlas = metadata?.atlases?.[atlasKey] || {key: atlasKey, label: atlasKey};
                      return (
                        <span
                          key={atlasKey}
                          className="group/chip inline-flex items-center gap-1.5 rounded-md border border-cursor-hairline bg-cursor-surface-card py-0.5 pl-2.5 pr-1 text-xs font-medium text-cursor-ink transition-all hover:border-cursor-hairline-strong shadow-2xs"
                        >
                          <span className="truncate max-w-[20rem]">{atlas.label || atlas.key}</span>
                          <button
                            type="button"
                            onClick={() => removeAtlas(statKey, atlas.key)}
                            className="flex h-4.5 w-4.5 items-center justify-center rounded text-cursor-muted hover:bg-cursor-hairline hover:text-cursor-ink transition-colors"
                            aria-label={`Remove atlas ${atlas.label || atlas.key}`}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      );
                    })
                  ) : (
                    <span className="text-xs text-cursor-muted italic">
                      No atlases selected for this metric.
                    </span>
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
        const pickerLabel =
          pickerStat?.label ||
          atlasPickerStatKey
            .split('_')
            .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
        const filteredAtlasKeys = pickerAtlasKeys.filter((atlasKey) => {
          const atlas = metadata?.atlases?.[atlasKey] || {key: atlasKey, label: atlasKey};
          const query = atlasSearch.trim().toLowerCase();
          if (!query) return true;
          return `${atlas.label || ''} ${atlas.key || atlasKey}`.toLowerCase().includes(query);
        });

        return (
          <ModalOverlay onClose={() => { setAtlasPickerStatKey(null); setAtlasSearch(''); }}>
            <div className="flex flex-col max-h-[85vh]">
              {/* Modal Header */}
              <div className="flex items-center justify-between gap-3 border-b border-cursor-hairline pb-2.5 flex-none">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cursor-primary/10 text-cursor-primary flex-none">
                    <Layers className="h-4 w-4" />
                  </div>
                  <h3 id="atlas-picker-title" className="m-0 text-base font-semibold leading-tight text-cursor-ink">
                    Add Atlas to {pickerLabel}
                  </h3>
                </div>
                <div className="flex items-center gap-1.5 flex-none">
                  <span className="inline-flex items-center rounded-full bg-cursor-primary/10 border border-cursor-primary/20 px-2 py-0.25 text-2xs font-semibold text-cursor-primary">
                    {pickerSelectedAtlases.length} selected
                  </span>
                  <button
                    type="button"
                    onClick={() => { setAtlasPickerStatKey(null); setAtlasSearch(''); }}
                    className="flex h-6 w-6 items-center justify-center rounded-md text-cursor-muted hover:bg-cursor-canvas hover:text-cursor-ink transition-colors"
                    aria-label="Close dialog"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {/* Search Bar */}
              <div className="relative my-2.5 flex-none">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-cursor-muted" />
                <input
                  type="text"
                  value={atlasSearch}
                  onChange={(e) => setAtlasSearch(e.target.value)}
                  placeholder="Search atlases..."
                  autoFocus
                  className="w-full rounded-md border border-cursor-hairline bg-cursor-canvas-soft h-8 px-2.5 pl-8 pr-8 text-sm text-cursor-ink placeholder:text-cursor-muted focus:border-cursor-primary focus:bg-cursor-surface-card focus:outline-none focus:ring-1 focus:ring-cursor-primary transition-all"
                />
                {atlasSearch && (
                  <button
                    type="button"
                    onClick={() => setAtlasSearch('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-cursor-muted hover:text-cursor-ink"
                    title="Clear search"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              {/* Atlases List */}
              <div className="max-h-[22rem] space-y-1.5 overflow-y-auto pr-1">
                {filteredAtlasKeys.length ? (
                  filteredAtlasKeys.map((atlasKey) => {
                    const atlas = metadata?.atlases?.[atlasKey] || {key: atlasKey, label: atlasKey};
                    const isSelected = pickerSelectedAtlases.includes(atlasKey);
                    return (
                      <button
                        key={atlasKey}
                        type="button"
                        onClick={() => toggleAtlas(atlasPickerStatKey, atlasKey)}
                        className={`group flex w-full cursor-pointer items-center justify-between gap-2.5 rounded-md border px-2.5 py-2 text-left transition-all ${
                          isSelected
                            ? 'border-cursor-primary/50 bg-cursor-primary/[0.04] text-cursor-ink hover:bg-cursor-primary/[0.08]'
                            : 'border-cursor-hairline bg-cursor-surface-card text-cursor-ink hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0 flex-1">
                          <div
                            className={`flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded transition-colors ${
                              isSelected
                                ? 'bg-cursor-primary text-white'
                                : 'border border-cursor-hairline-strong bg-cursor-surface-card group-hover:border-cursor-primary'
                            }`}
                          >
                            {isSelected ? <Check className="h-3 w-3" strokeWidth={3} /> : null}
                          </div>
                          <div className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-semibold text-cursor-ink">
                              {atlas.label || atlas.key}
                            </span>
                            <span className="block truncate font-mono text-2xs text-cursor-muted">
                              {atlas.key}
                            </span>
                          </div>
                        </div>

                        <div className="flex-none">
                          {isSelected ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-cursor-primary/10 border border-cursor-primary/20 px-2 py-0.25 text-2xs font-semibold text-cursor-primary">
                              Selected
                            </span>
                          ) : (
                            <span className="opacity-0 group-hover:opacity-100 inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-surface-card px-2 py-0.25 text-2xs font-medium text-cursor-body transition-opacity">
                              + Select
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })
                ) : (
                  <p className="py-6 text-center text-xs italic text-cursor-muted">
                    No atlases match "{atlasSearch}".
                  </p>
                )}
              </div>

              {/* Modal Footer */}
              <div className="mt-3 pt-2.5 border-t border-cursor-hairline-soft flex items-center justify-end flex-none">
                <button
                  type="button"
                  onClick={() => { setAtlasPickerStatKey(null); setAtlasSearch(''); }}
                  className="inline-flex h-7.5 items-center justify-center rounded-md bg-cursor-primary px-4 text-xs font-semibold text-white transition-colors hover:bg-cursor-primary-active"
                >
                  Done
                </button>
              </div>
            </div>
          </ModalOverlay>
        );
      })()}
    </Panel>
  );
}

function InfoTooltip({content}: {content: React.ReactNode}) {
  return (
    <Tooltip>
      <TooltipTrigger
        type="button"
        className="inline-flex items-center justify-center text-cursor-muted hover:text-cursor-ink transition-colors cursor-help p-0.5"
        onClick={(e) => e.stopPropagation()}
      >
        <Info className="h-3 w-3" />
      </TooltipTrigger>
      <TooltipContent side="top" align="center" className="max-w-xs text-xs leading-relaxed font-normal">
        {content}
      </TooltipContent>
    </Tooltip>
  );
}

export function AdvancedSettingsSection() {
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);
  const neuroflowEnabled = formValues.neuroflowEnabled !== undefined ? Boolean(formValues.neuroflowEnabled) : true;
  const neuroflowWarmupEnabled = Boolean(formValues.neuroflowWarmupEnabled);
  const [showAdvancedDetails, setShowAdvancedDetails] = React.useState(false);

  return (
    <Panel
      icon={<SlidersHorizontal className="h-4 w-4 text-cursor-primary" />}
      title="Advanced Settings"
      titleRight={
        neuroflowEnabled ? (
          <span className="rounded-full bg-cursor-primary/10 px-2 py-0.5 text-2xs font-semibold text-cursor-primary uppercase tracking-wide">
            Adaptive DAG
          </span>
        ) : null
      }
      className="min-w-0"
    >
      <TooltipProvider>
        <div className="grid gap-3">
          {/* Master Toggle Card */}
          <div className="rounded-lg border border-cursor-hairline bg-cursor-canvas-soft/40 p-3">
            <label className="flex cursor-pointer items-center justify-between gap-2.5">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={neuroflowEnabled}
                  onChange={(e) => setFormField('neuroflowEnabled', e.target.checked)}
                  className="h-4 w-4 accent-cursor-primary cursor-pointer"
                />
                <span className="text-sm font-medium text-cursor-ink">Enable NeuroFLOW Dynamic Scheduler</span>
                <InfoTooltip content="Optimizes multi-subject pipeline runs with adaptive concurrency, memory forecasting, and automatic fault recovery." />
              </div>
            </label>
          </div>

          {neuroflowEnabled && (
            <div className="grid gap-3">
              {/* Core Scheduling Group */}
              <div className="grid grid-cols-2 gap-3">
                <label className={labelCls}>
                  <span className="flex items-center gap-1.5 font-medium text-cursor-ink">
                    <Zap className="h-3.5 w-3.5 text-cursor-primary" />
                    Max Concurrent Tasks
                    <InfoTooltip content="Maximum number of parallel pipeline stages running simultaneously across all subjects." />
                  </span>
                  <input
                    type="number"
                    min={1}
                    step={1}
                    value={formValues.neuroflowMaxConcurrentTasks ?? 2}
                    onChange={(e) => setFormField('neuroflowMaxConcurrentTasks', Math.max(1, parseInt(e.target.value, 10) || 1))}
                    className={inputCls}
                  />
                </label>

                <label className={labelCls}>
                  <span className="flex items-center gap-1.5 font-medium text-cursor-ink">
                    <RefreshCw className="h-3.5 w-3.5 text-cursor-primary" />
                    Max Retries Per Task
                    <InfoTooltip content="Maximum retry attempts with exponential backoff if a stage encounters a temporary failure (0 = disabled)." />
                  </span>
                  <input
                    type="number"
                    min={0}
                    max={5}
                    step={1}
                    value={formValues.neuroflowMaxRetries ?? 3}
                    onChange={(e) => setFormField('neuroflowMaxRetries', Math.max(0, parseInt(e.target.value, 10) || 0))}
                    className={inputCls}
                  />
                </label>
              </div>

              {/* Safe Warm-up Card */}
              <div className="rounded-lg border border-cursor-hairline bg-cursor-canvas-soft/30 p-3">
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={neuroflowWarmupEnabled}
                    onChange={(e) => setFormField('neuroflowWarmupEnabled', e.target.checked)}
                    className="h-3.5 w-3.5 accent-cursor-primary cursor-pointer"
                  />
                  <span className="text-xs font-medium text-cursor-ink">Safe Warm-up Mode (Adaptive Scaling)</span>
                  <InfoTooltip content="Starts execution conservatively with fewer parallel tasks, then automatically scales up concurrency after initial stages complete without memory pressure." />
                </label>

                {neuroflowWarmupEnabled && (
                  <div className="mt-2.5 grid grid-cols-2 gap-3 pl-5 pt-2 border-t border-cursor-hairline/60">
                    <label className={labelCls}>
                      <span className="flex items-center gap-1 text-xs text-cursor-ink">
                        Initial Concurrency
                        <InfoTooltip content="Starting concurrency slot count during the warm-up phase." />
                      </span>
                      <input
                        type="number"
                        min={1}
                        step={1}
                        value={formValues.neuroflowWarmupInitialConcurrency ?? 1}
                        onChange={(e) => setFormField('neuroflowWarmupInitialConcurrency', Math.max(1, parseInt(e.target.value, 10) || 1))}
                        className={inputCls}
                      />
                    </label>

                    <label className={labelCls}>
                      <span className="flex items-center gap-1 text-xs text-cursor-ink">
                        Successes to Scale Up
                        <InfoTooltip content="Number of consecutive stable stage completions required before increasing concurrency." />
                      </span>
                      <input
                        type="number"
                        min={1}
                        step={1}
                        value={formValues.neuroflowWarmupSafeSuccesses ?? 3}
                        onChange={(e) => setFormField('neuroflowWarmupSafeSuccesses', Math.max(1, parseInt(e.target.value, 10) || 1))}
                        className={inputCls}
                      />
                    </label>
                  </div>
                )}
              </div>

              {/* Advanced Toggle / Collapsible */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowAdvancedDetails(!showAdvancedDetails)}
                  className="flex items-center gap-1.5 text-xs font-medium text-cursor-primary hover:text-cursor-primary-active transition-colors cursor-pointer"
                >
                  {showAdvancedDetails ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  {showAdvancedDetails ? 'Hide Tuning & Safeguards' : 'Show Tuning & Safeguards (Memory, I/O, Profile)'}
                </button>

                {showAdvancedDetails && (
                  <div className="mt-2.5 grid gap-3 rounded-lg border border-cursor-hairline bg-cursor-canvas-soft/30 p-3">
                    {/* Memory & Estimation */}
                    <div className="grid grid-cols-2 gap-3">
                      <label className={labelCls}>
                        <span className="flex items-center gap-1.5 font-medium text-cursor-ink">
                          <Gauge className="h-3.5 w-3.5 text-cursor-primary" />
                          Estimation Risk Profile
                          <InfoTooltip content="Controls resource prediction margins. Balanced (90th percentile), Conservative (95th percentile - maximizes safety against OOM), Aggressive (75th percentile - maximizes task density)." />
                        </span>
                        <select
                          value={formValues.neuroflowEstimationMode ?? 'balanced'}
                          onChange={(e) => setFormField('neuroflowEstimationMode', e.target.value as 'balanced' | 'conservative' | 'aggressive')}
                          className={inputCls}
                        >
                          <option value="balanced">Balanced (90th percentile - Standard)</option>
                          <option value="conservative">Conservative (95th percentile - Safe RAM)</option>
                          <option value="aggressive">Aggressive (75th percentile - Max packing)</option>
                        </select>
                      </label>

                      <label className={labelCls}>
                        <span className="flex items-center gap-1.5 font-medium text-cursor-ink">
                          <HardDrive className="h-3.5 w-3.5 text-cursor-primary" />
                          Max I/O-Heavy Tasks
                          <InfoTooltip content="Limits concurrent disk-intensive operations (such as volume reconstruction or file decompression) to prevent disk I/O bottlenecks." />
                        </span>
                        <input
                          type="number"
                          min={1}
                          step={1}
                          value={formValues.neuroflowMaxIoHeavyTasks ?? 2}
                          onChange={(e) => setFormField('neuroflowMaxIoHeavyTasks', Math.max(1, parseInt(e.target.value, 10) || 1))}
                          className={inputCls}
                        />
                      </label>
                    </div>

                    {/* Machine Profile */}
                    <label className={labelCls}>
                      <span className="flex items-center gap-1.5 font-medium text-cursor-ink">
                        <Cpu className="h-3.5 w-3.5 text-cursor-primary" />
                        Machine Profile Identifier
                        <InfoTooltip content="Hardware benchmark profile ID (e.g. application_default, workstation_32c) used to calibrate runtime and memory priors." />
                      </span>
                      <input
                        type="text"
                        value={formValues.neuroflowMachineProfileId ?? 'application_default'}
                        onChange={(e) => setFormField('neuroflowMachineProfileId', e.target.value)}
                        placeholder="application_default"
                        className={inputCls}
                      />
                    </label>

                    {/* OOM Protection Checkbox */}
                    <label className="flex cursor-pointer items-center gap-2 pt-1 border-t border-cursor-hairline/60">
                      <input
                        type="checkbox"
                        checked={formValues.neuroflowPreserveOomBounds !== undefined ? Boolean(formValues.neuroflowPreserveOomBounds) : true}
                        onChange={(e) => setFormField('neuroflowPreserveOomBounds', e.target.checked)}
                        className="h-3.5 w-3.5 accent-cursor-primary cursor-pointer"
                      />
                      <span className="text-xs font-medium text-cursor-ink">Preserve OOM Memory Bounds</span>
                      <InfoTooltip content="Remembers peak RAM thresholds if a container crashes due to Out-Of-Memory (OOM exit code 137) to automatically grant higher memory limits on subsequent retries." />
                    </label>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </TooltipProvider>
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/35 p-3"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-[32rem] rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 shadow-none">
        {children}
      </div>
    </div>
  );
}

function ModalTitle({children}: {children: React.ReactNode}) {
  return <h3 className="m-0 mb-3 text-sm font-semibold leading-[1.3] text-cursor-ink">{children}</h3>;
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
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-cursor-ink/30 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative my-auto w-full max-w-[min(52rem,calc(100vw-2rem))] rounded-xl border border-cursor-hairline bg-cursor-surface-card shadow-none">
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
      <div className="border-b border-cursor-hairline px-4 py-2.5">
        <h3 className="m-0 text-base font-semibold text-cursor-ink">{title}</h3>
        {/* Path bar */}
        <div className="mt-2 flex gap-1.5">
          <input
            className={`${inputCls} min-w-0 flex-1 font-mono text-xs`}
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
            className="inline-flex h-8 flex-none cursor-pointer items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card px-3 text-xs font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-50"
          >
            Go
          </button>
        </div>
      </div>

      {/* Entry list */}
      <div className="max-h-[min(24rem,55vh)] overflow-y-auto bg-cursor-canvas-soft">
        {/* Up row */}
        {parentPath !== currentPath && !isLoading && (
          <button
            type="button"
            onClick={() => doBrowse(parentPath)}
            className="flex w-full items-center gap-2.5 border-b border-cursor-hairline-soft px-4 py-1.5 text-left text-xs text-cursor-primary hover:bg-cursor-surface-card"
          >
            <span className="inline-flex h-4.5 w-7 flex-none items-center justify-center rounded text-2xs font-semibold uppercase tracking-wide text-cursor-muted">
              UP
            </span>
            <span className="min-w-0 flex-1 truncate font-mono">..</span>
          </button>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-8 text-xs text-cursor-muted">Loading...</div>
        )}

        {/* Error */}
        {!isLoading && isError && statusMsg && (
          <div className="px-4 py-3 text-xs text-cursor-semantic-error">{statusMsg}</div>
        )}

        {/* Empty */}
        {!isLoading && !isError && entries.length === 0 && (
          <div className="flex items-center justify-center py-8 text-xs text-cursor-muted">
            Empty directory.
          </div>
        )}

        {/* Directories */}
        {!isLoading &&
          dirs.map((entry) => {
            const isDcm = entry.is_dicom_series;
            const badge = isDcm ? `DCM (${entry.slice_count ?? '?'} sl)` : 'DIR';
            return (
              <button
                key={entry.path}
                type="button"
                title={entry.path}
                onClick={() => {
                  if (selectMode === 'path') setManualPath(entry.path);
                  doBrowse(entry.path);
                }}
                className="flex w-full items-center gap-2.5 border-b border-cursor-hairline-soft px-4 py-1.5 text-left text-xs hover:bg-cursor-surface-card"
              >
                <span
                  className={`inline-flex h-4.5 min-w-7 px-1.5 flex-none items-center justify-center rounded text-2xs font-semibold uppercase tracking-wide ${
                    isDcm ? 'bg-cursor-primary/10 text-cursor-primary' : 'bg-cursor-primary/10 text-cursor-primary'
                  }`}
                >
                  {badge}
                </span>
                <span className="min-w-0 flex-1 truncate font-medium text-cursor-ink">{entry.name}</span>
                {entry.size != null && (
                  <span className="flex-none text-right text-cursor-muted text-xs" style={{minWidth: '4rem'}}>
                    {fmtBytes(entry.size)}
                  </span>
                )}
              </button>
            );
          })}

        {/* Files */}
        {!isLoading &&
          files.map((entry) => {
            const checked = selectedFiles.has(entry.path);
            const isImg = entry.selectable;
            const lower = entry.name.toLowerCase();
            const badge = lower.endsWith('.nii.gz') || lower.endsWith('.nii')
              ? 'NII'
              : lower.endsWith('.mgz') || lower.endsWith('.mgh')
              ? 'MGZ'
              : lower.endsWith('.dcm') || lower.endsWith('.dicom')
              ? 'DCM'
              : isImg
              ? 'IMG'
              : 'FILE';
            const badgeCls = isImg
              ? 'bg-cursor-primary/8 text-cursor-primary'
              : 'bg-cursor-canvas text-cursor-muted';
            return (
              <div
                key={entry.path}
                className="flex w-full items-center gap-2.5 border-b border-cursor-hairline-soft px-4 py-1.5 text-xs"
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
                  className={`inline-flex h-4.5 min-w-7 px-1 flex-none items-center justify-center rounded text-2xs font-semibold uppercase tracking-wide ${badgeCls}`}
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
                  <span className="flex-none text-right text-cursor-muted text-xs" style={{minWidth: '4rem'}}>
                    {fmtBytes(entry.size)}
                  </span>
                )}
              </div>
            );
          })}
      </div>

      {/* Sticky footer */}
      <div className="flex items-center justify-between gap-2.5 border-t border-cursor-hairline px-4 py-2.5">
        {selectMode === 'files' ? (
          <span className="text-xs text-cursor-muted">{selectedFiles.size} file(s) selected</span>
        ) : (
          <span className="min-w-0 truncate font-mono text-xs text-cursor-muted" title={manualPath || currentPath}>
            {manualPath || currentPath}
          </span>
        )}
        <div className="flex flex-none gap-1.5">
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
      {/* Header */}
      <div className="border-b border-cursor-hairline px-4 py-2.5">
        <h3 className="m-0 text-base font-semibold text-cursor-ink">Configure Batch Settings</h3>
        <p className="mt-0.5 text-xs text-cursor-muted">
          {isServer && !isConnected
            ? 'Connect to the server first to scan the directory.'
            : `Input path: ${inputPath || '(not set)'}`}
        </p>
      </div>

      {/* Scan controls */}
      {canScan && (
        <div className="border-b border-cursor-hairline px-4 py-2.5">
          <div className="mb-1.5 flex items-center justify-between">
            <p className="text-sm font-medium text-cursor-body">Scan mode</p>
            <button
              type="button"
              onClick={() => doScan(scanMode, true)}
              disabled={scanPending}
              className="rounded-md border border-cursor-hairline bg-cursor-surface-card px-2.5 py-1 text-xs font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              Re-scan
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {SCAN_MODE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  setScanMode(opt.value);
                  doScan(opt.value);
                }}
                title={opt.hint}
                className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors ${
                  scanMode === opt.value
                    ? 'border-cursor-primary bg-cursor-primary text-white'
                    : 'border-cursor-hairline bg-cursor-surface-card text-cursor-ink hover:border-cursor-hairline-strong'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {scanStatus && (
            <p className={`mt-1.5 text-xs ${hasConflict ? 'text-cursor-semantic-error' : 'text-cursor-muted'}`}>
              {scanStatus}
              {hasConflict && ' Multiple images found for some subjects - review selections below.'}
            </p>
          )}
        </div>
      )}

      {/* Candidate list */}
      {canScan && serverEntries.length > 0 && (
        <TooltipProvider>
          <div className="max-h-[min(20rem,50vh)] overflow-y-auto bg-cursor-canvas-soft">
            {/* Table header */}
          <div className="grid border-b border-cursor-hairline px-4 py-1.5 text-2xs font-semibold uppercase tracking-wide text-cursor-muted" style={{gridTemplateColumns: '1.5rem minmax(8rem,1.5fr) minmax(5.5rem,1fr) minmax(8rem,1.6fr) minmax(10rem,2.2fr) 4.5rem'}}>
            <span />
            <span>Subject</span>
            <span>Format</span>
            <span>Name</span>
            <span>Relative path</span>
            <span className="text-right">Size</span>
          </div>
          {serverEntries.map((entry) => {
            const checked = selectedPaths.has(entry.path);
            const lower = entry.name.toLowerCase();
            const formatBadge = entry.is_dicom_series ? (
              <Tooltip>
                <TooltipTrigger className="min-w-0 text-left">
                  <span className="inline-flex items-center rounded bg-cursor-primary/10 px-1.5 py-0.5 text-2xs font-semibold text-cursor-primary">
                    DCM ({entry.slice_count ?? '?'} sl)
                  </span>
                </TooltipTrigger>
                <TooltipContent side="bottom" align="start" className="text-xs">
                  DICOM Series ({entry.slice_count ?? '?'} slices)
                </TooltipContent>
              </Tooltip>
            ) : (
              <span className="inline-flex items-center rounded border border-cursor-hairline bg-cursor-surface-card px-1.5 py-0.5 text-2xs font-semibold text-cursor-muted">
                {lower.endsWith('.nii.gz') || lower.endsWith('.nii')
                  ? 'NII'
                  : lower.endsWith('.mgz') || lower.endsWith('.mgh')
                  ? 'MGZ'
                  : lower.endsWith('.dcm') || lower.endsWith('.dicom')
                  ? 'DCM'
                  : 'IMG'}
              </span>
            );
            return (
              <div
                key={entry.path}
                role="button"
                tabIndex={0}
                onClick={() => togglePath(entry.path)}
                onKeyDown={(e) => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); togglePath(entry.path); } }}
                className="grid cursor-pointer items-center border-b border-cursor-hairline-soft px-4 py-1.5 hover:bg-cursor-surface-card"
                style={{gridTemplateColumns: '1.5rem minmax(8rem,1.5fr) minmax(5.5rem,1fr) minmax(8rem,1.6fr) minmax(10rem,2.2fr) 4.5rem'}}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  readOnly
                  className="h-3.5 w-3.5 accent-cursor-primary pointer-events-none"
                />
                <Tooltip>
                  <TooltipTrigger className="min-w-0 w-full text-left">
                    <span className="block min-w-0 truncate pr-2 text-xs font-medium text-cursor-ink">
                      {entry.subject_label ?? '-'}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" align="start" className="max-w-md break-all text-xs">
                    {entry.subject_label ?? '-'}
                  </TooltipContent>
                </Tooltip>
                <div className="flex items-center">{formatBadge}</div>
                <span className="min-w-0 truncate pr-2 font-mono text-xs text-cursor-ink">
                  {entry.name}
                </span>
                <Tooltip>
                  <TooltipTrigger className="min-w-0 w-full text-left block">
                    <span className="block min-w-0 truncate pr-2 font-mono text-2xs text-cursor-muted">
                      {entry.relative_path ?? ''}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" align="start" className="max-w-md break-all text-xs">
                    {entry.relative_path ?? entry.path}
                  </TooltipContent>
                </Tooltip>
                <span className="text-right text-2xs text-cursor-muted">{fmtBytes(entry.size)}</span>
              </div>
            );
          })}
          </div>
        </TooltipProvider>
      )}

      {/* Manual count fallback (local or not yet scanned) */}
      <div className="px-4 py-2.5">
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
          <div className="flex items-center justify-between gap-2.5">
            <p className="text-xs text-cursor-muted">{selectedPaths.size} selected</p>
            <div className="flex gap-2">
              {selectedPaths.size !== serverEntries.length && (
                <button
                  type="button"
                  onClick={() => setSelectedPaths(new Set(serverEntries.map((e) => e.path)))}
                  className="text-xs text-cursor-primary hover:underline"
                >
                  Select all
                </button>
              )}
              {selectedPaths.size > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedPaths(new Set())}
                  className="text-xs text-cursor-primary hover:underline"
                >
                  Unselect all
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex justify-end gap-1.5 border-t border-cursor-hairline px-4 py-2.5">
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
  browseLabel = 'Browse',
  secondaryBrowse,
  required,
}: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  onChange: (v: string) => void;
  onBrowse: () => void;
  browseLabel?: string;
  secondaryBrowse?: {
    label: string;
    onClick: () => void;
    title?: string;
  };
  required?: boolean;
}) {
  return (
    <label className={labelCls}>
      {label}
      <div className="flex gap-1.5">
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
          title={browseLabel}
          className="inline-flex h-8 flex-none cursor-pointer items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card px-2.5 text-xs font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft"
        >
          {browseLabel}
        </button>
        {secondaryBrowse && (
          <button
            type="button"
            onClick={secondaryBrowse.onClick}
            title={secondaryBrowse.title ?? secondaryBrowse.label}
            className="inline-flex h-8 flex-none cursor-pointer items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card px-2.5 text-xs font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft"
          >
            {secondaryBrowse.label}
          </button>
        )}
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
    <div className="flex flex-col gap-1.5">
      {options.map((opt) => (
        <label
          key={opt.value}
          className={`flex cursor-pointer items-start gap-2 rounded-md border px-2.5 py-1.5 transition-colors ${
            value === opt.value
              ? 'border-cursor-primary bg-cursor-canvas-soft'
              : 'border-cursor-hairline bg-cursor-surface-card hover:border-cursor-hairline-strong'
          } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
        >
          <input
            type="radio"
            name={name}
            value={opt.value}
            checked={value === opt.value}
            disabled={disabled}
            onChange={() => !disabled && onChange(opt.value)}
            className="mt-0.5 h-3.5 w-3.5 flex-none accent-cursor-primary"
          />
          <span className="grid gap-0.25">
            <span className="text-sm font-medium leading-[1.3] text-cursor-ink">{opt.label}</span>
            {opt.hint && <span className="text-xs leading-[1.3] text-cursor-muted">{opt.hint}</span>}
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
    {label: 'Single input', value: 'file', hint: 'Process one NIfTI file or DICOM series folder.'},
    {label: 'Batch input', value: 'batch_folder', hint: 'Process a folder of images or DICOM series.'},
  ];

  // Source radio options
  const sourceOptions = [
    {label: 'Local', value: 'Local', hint: 'Files on this machine.'},
    {label: 'Server', value: 'Server', hint: 'Files on the remote server.'},
  ];

  const handleLocalBrowseFile = async () => {
    if (!hasTauriInternals()) {
      localInputRef.current?.click();
      return;
    }
    try {
      const selected = await open({
        multiple: false,
        filters: [{name: 'MRI Images', extensions: ['nii.gz', 'nii', 'mgz', 'mgh', 'dcm', 'dicom', 'ima', '*']}],
      });
      const path = selectedDialogPath(selected);
      if (path) {
        setFormField('inputPath', path);
      }
    } catch {
      // dialog cancelled or unavailable
    }
  };

  const handleLocalBrowseFolder = async () => {
    if (!hasTauriInternals()) {
      alert('Folder picker is not available in browser mode. Please type the folder path manually.');
      return;
    }
    try {
      const selected = await open({directory: true, multiple: false});
      const path = selectedDialogPath(selected);
      if (path) {
        setFormField('inputPath', path);
      }
    } catch {
      // dialog cancelled or unavailable
    }
  };

  const handleLocalBrowseOutputDir = async () => {
    if (!hasTauriInternals()) {
      alert('Directory picker is not available in browser mode. Please type the path manually.');
      return;
    }
    try {
      const selected = await open({directory: true, multiple: false});
      const path = selectedDialogPath(selected);
      if (path) {
        setFormField('outputDir', path);
      }
    } catch {
      // dialog cancelled or unavailable
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
      <Panel icon={<FolderInput className="h-4 w-4 text-cursor-primary" />} title="Input & Output" className="min-w-0">
        <div className="grid gap-4">
          {/* Row 1: Source + Input Mode */}
          <div className="grid gap-4 grid-cols-2 items-start">
            {/* Source */}
            <div className="grid gap-2">
              <span className="text-sm font-medium leading-[1.3] text-cursor-body">Source Input</span>
              <RadioGroup
                name="inputSource"
                options={sourceOptions}
                value={inputSource}
                onChange={(v) => setFormField('inputSource', v)}
                disabled={isLocal}
              />
              {isLocal && (
                <p className="text-2xs leading-[1.3] text-cursor-muted">
                  Server source is unavailable when Runtime Target is Local.
                </p>
              )}
              {isServerSource && remoteConnected && (
                <div className="flex items-center gap-2">
                  <Button variant="ghost" icon={<Upload className="h-3.5 w-3.5" />} onClick={handleUploadToServer}>
                    Upload data to server
                  </Button>
                  {uploadNotice && (
                    <span className="text-xs text-cursor-muted">Not wired yet - upload feature coming soon.</span>
                  )}
                </div>
              )}
            </div>

            {/* Input Mode */}
            <div className="grid gap-2">
              <span className="text-sm font-medium leading-[1.3] text-cursor-body">Input Mode</span>
              <RadioGroup
                name="inputMode"
                options={inputModeOptions}
                value={isBatch ? 'batch_folder' : 'file'}
                onChange={(v) => setFormField('inputMode', v)}
              />
              {isBatch && (
                <div className="flex items-center gap-2">
                  <Button variant="ghost" icon={<SlidersHorizontal className="h-3.5 w-3.5" />} onClick={() => setBatchModal(true)}>
                    Configure batch
                  </Button>
                  {formValues.batchImageCount !== undefined && (
                    <span className="text-xs text-cursor-muted">{formValues.batchImageCount} selected</span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-cursor-hairline-soft" />

          {/* Server not-connected notice */}
          {isServerSource && !remoteConnected && (
            <div className="rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft px-3 py-2">
              <p className="text-xs font-medium text-cursor-ink">SSH not connected</p>
              <p className="mt-0.5 text-xs text-cursor-muted">
                Connect in the SSH Server card below to enable server browsing.
              </p>
            </div>
          )}

          {/* Row 2: Path fields — Local */}
          {inputSource === 'Local' && (
            <div className="grid gap-3">
              {isBatch ? (
                <PathField
                  id="inputPath"
                  label="Input location"
                  value={formValues.inputPath}
                  placeholder="/data/batch_subjects_folder"
                  onChange={(v) => setFormField('inputPath', v)}
                  onBrowse={handleLocalBrowseFolder}
                  browseLabel="Browse Folder"
                  required
                />
              ) : (
                <PathField
                  id="inputPath"
                  label="Input location"
                  value={formValues.inputPath}
                  placeholder="/data/sub-001_T1w.nii.gz or /data/dicom_series_folder"
                  onChange={(v) => setFormField('inputPath', v)}
                  onBrowse={handleLocalBrowseFile}
                  browseLabel="Browse File"
                  secondaryBrowse={{
                    label: 'Folder (DICOM)',
                    title: 'Browse DICOM series folder',
                    onClick: handleLocalBrowseFolder,
                  }}
                  required
                />
              )}
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
                onBrowse={handleLocalBrowseOutputDir}
                required
              />
            </div>
          )}

          {/* Row 2: Path fields — Server */}
          {inputSource === 'Server' && (
            <div className="grid gap-3">
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
            className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-3"
            onMouseDown={() => setServerInputModal(false)}
          >
            <div className="rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 max-w-sm w-full">
              <h3 className="m-0 mb-2 text-sm font-semibold text-cursor-ink">SSH not connected</h3>
              <p className="text-xs text-cursor-muted">Connect in the SSH Server card first, then browse.</p>
              <div className="mt-3 flex justify-end">
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
            className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-3"
            onMouseDown={() => setServerOutputModal(false)}
          >
            <div className="rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 max-w-sm w-full">
              <h3 className="m-0 mb-2 text-sm font-semibold text-cursor-ink">SSH not connected</h3>
              <p className="text-xs text-cursor-muted">Connect in the SSH Server card first, then browse.</p>
              <div className="mt-3 flex justify-end">
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
        <div className="grid min-h-0 h-full content-start gap-4 overflow-y-auto pl-4 pt-4 pb-4 pr-3 [scrollbar-gutter:stable]">
          <PipelineStepsSection />
          <StatsAtlasSection />
          <AdvancedSettingsSection />
        </div>
      }
      right={
        <div className="grid min-h-0 h-full content-start gap-4 overflow-y-auto pl-3 pt-4 pb-4 pr-4 [scrollbar-gutter:stable]">
          <InputOutputSection />
          <RuntimeSection />
        </div>
      }
    />
  );
}


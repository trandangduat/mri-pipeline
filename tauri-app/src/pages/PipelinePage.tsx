import React, {useRef} from 'react';
import {Workflow, FolderInput, FolderOpen, Save, Play, Square, Loader2, FileKey, Upload, SlidersHorizontal, Eye, EyeOff, Layers, Plus, Check, X, Search, BarChart3, Zap, RefreshCw, Gauge, HardDrive, Cpu, Info, ListOrdered, ChevronDown} from 'lucide-react';
import {open} from '@tauri-apps/plugin-dialog';
import {useNavigate} from 'react-router';
import {Panel, Button, Alert, inputCls, labelCls} from '../components/ui';
import {EMPTY_STAGE_VIOLATIONS, validateStageTools} from '../lib/stageValidation';
import {Tooltip, TooltipTrigger, TooltipContent, TooltipProvider} from '@/components/ui/tooltip';
import {SplitPaneForm} from '../components/SplitPaneForm';
import {RuntimeSection} from '../components/RuntimeSection';
import {StartPipelineDialog} from '../components/StartPipelineDialog';
import {DualPaneTransferModal} from '../components/DualPaneTransferModal';
import {useStartPipelineStream} from '../hooks/useStartPipelineStream';
import {useMetadata, useClient} from '../query/useEnvironment';
import {useRemoteBrowseMutation, useLocalBrowseMutation} from '../query/useRemote';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useJobsStore} from '../stores/jobsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {buildRunConfig, buildRemotePayload, NEUROFLOW_PIPELINE_CONFIGS, neuroflowConfigFilesForMode, type RemotePayload} from '../api/runConfig';
import {presetDefaultAtlases} from '../lib/pipelinePresets';
import {buildPresetPayload, defaultConfigName, saveJsonAsDialog} from '../lib/configExport';
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
  const setSelectedStatsAtlases = usePipelineFormStore((s) => s.setSelectedStatsAtlases);

  const licensePath = usePipelineFormStore((s) => s.formValues.licensePath as string | undefined);
  const licenseFileInput = useRef<HTMLInputElement>(null);
  const [uploadingLicense, setUploadingLicense] = React.useState(false);
  const [showTools, setShowTools] = React.useState(formValues.pipelineMode === 'Custom');
  const [presetInvalid, setPresetInvalid] = React.useState(false);

  // Automatically show tools when switching to Custom mode
  React.useEffect(() => {
    if (formValues.pipelineMode === 'Custom') {
      setShowTools(true);
    }
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

  const stageViolations = React.useMemo(
    () => (metadata ? validateStageTools(metadata, formValues) : EMPTY_STAGE_VIOLATIONS),
    [metadata, formValues],
  );
  const invalidStageIds = React.useMemo(
    () => new Set(stageViolations.map((violation) => violation.stageId)),
    [stageViolations],
  );

  const presetFileInput = useRef<HTMLInputElement>(null);

  const print = (label: string, payload: unknown) => {
    const output = useJobsStore.getState().appendOutput;
    output(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  };

  const handleSavePreset = async () => {
    const payload = buildPresetPayload(metadata, formValues);
    const selectedTools = payload.selected_tools as Record<string, string>;
    if (!selectedTools || Object.keys(selectedTools).length === 0) {
      print('Save preset', {ok: false, error: 'Select at least one pipeline tool before saving a preset.'});
      return;
    }
    const result = await saveJsonAsDialog(defaultConfigName('neuroflow-preset'), payload);
    if (result.ok) {
      print('Saved preset file', {ok: true, path: result.path});
    } else if (!result.cancelled) {
      print('Save preset failed', {ok: false, error: result.error});
    }
  };

  const handlePipelineModeChange = (mode: string) => {
    if (mode === 'Custom') {
      setShowTools(true);
    }
    const preset = metadata?.presets?.[mode];
    if (preset) {
      const neuroflowFiles = neuroflowConfigFilesForMode(mode);
      const formFields: Record<string, string> = {
        pipelineMode: mode,
        neuroflowPresetFile: neuroflowFiles.preset,
        neuroflowProfileFile: neuroflowFiles.profile,
      };
      for (const stageKey of metadata?.stage_order || []) {
        formFields[`stage_${stageKey}`] = '';
      }
      for (const [stageKey, toolKey] of Object.entries(preset.tools || {})) {
        formFields[`stage_${stageKey}`] = toolKey;
      }
      setFormFields(formFields);
      setSelectedStatsAtlases(presetDefaultAtlases(metadata, mode));
    } else {
      setFormFields({pipelineMode: mode, neuroflowPresetFile: '', neuroflowProfileFile: ''});
    }
  };

  const handleStageToolChange = (stageId: string, toolKey: string) => {
    setShowTools(true);
    if (formValues.pipelineMode === 'Custom') {
      setFormField(`stage_${stageId}`, toolKey);
      return;
    }
    const preset = metadata?.presets?.[formValues.pipelineMode];
    const presetTool = preset?.tools?.[stageId] || '';
    if (toolKey === presetTool) {
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
      if (!preset || typeof preset !== 'object' || Array.isArray(preset)) {
        throw new Error('Preset file must contain a JSON object.');
      }
      if (
        !preset.selected_tools ||
        typeof preset.selected_tools !== 'object' ||
        Array.isArray(preset.selected_tools)
      ) {
        throw new Error(`"${file.name}" is not a valid preset file (missing "selected_tools" object).`);
      }
      const formFields: Record<string, unknown> = {pipelineMode: 'Custom'};
      for (const [k, v] of Object.entries(preset.selected_tools)) {
        formFields[`stage_${k}`] = v;
      }
      setFormFields(formFields);
      setShowTools(true);
      print('Loaded preset file', {name: file.name, selected_tools: preset.selected_tools});
    } catch {
      setPresetInvalid(true);
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
            onClick={handleSavePreset}
          >
            Save Preset
          </Button>
        </div>
        <input
          ref={presetFileInput}
          className="hidden"
          type="file"
          accept="application/json,.json"
          onChange={(e) => {
            handlePresetFile(e.target.files?.[0]);
            e.target.value = '';
          }}
        />
      </div>
      {metaLoading && (
        <div className="rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft px-3 py-4 text-center">
          <span className="text-xs text-cursor-muted">Connecting to backend&hellip;</span>
        </div>
      )}
      {metaError && !metaLoading && (
        <Alert severity="error">
          <p className="m-0 font-semibold text-sm">Backend unavailable</p>
          <p className="mt-1 text-sm text-cursor-muted">
            The MRI pipeline backend is not running. Start the dev server with{' '}
            <code className="rounded bg-cursor-canvas-soft px-1 font-mono text-2xs text-cursor-ink">npm run dev</code>{' '}
            from the <code className="rounded bg-cursor-canvas-soft px-1 font-mono text-2xs text-cursor-ink">tauri-app/</code>{' '}
            directory, which also starts the Python backend on port 8765.
          </p>
        </Alert>
      )}
      {!metaLoading && !metaError && showTools && (() => {
        const isCat12Preset = typeof formValues.pipelineMode === 'string' && formValues.pipelineMode.startsWith('CAT12 +');
        const displayedStages = (metadata?.stages || []).filter((stage) => {
          if (!isCat12Preset) return true;
          return ['segmentation', 'stats_extraction'].includes(stage.id);
        });

        return (
          <div className="grid border border-cursor-hairline rounded-md overflow-hidden">
            {displayedStages.length === 0 && (
              <div className="px-3 py-4 text-center text-xs text-cursor-muted">No pipeline stages found.</div>
            )}
            {displayedStages.map((stage) => {
              const tools = metadata?.tools_by_stage?.[stage.id] || [];
              const selectedToolKey = ((formValues as Record<string, unknown>)[`stage_${stage.id}`] as string) || '';
              const isUnavailable = selectedToolKey === '';
              const isInvalid = invalidStageIds.has(stage.id);
              const stageLabel = isCat12Preset
                ? stage.id === 'segmentation'
                  ? 'CAT12 Processing'
                  : stage.id === 'stats_extraction'
                    ? 'CAT12 Statistics'
                    : stage.label
                : stage.label;
              return (
                <div
                  key={stage.id}
                  className={`grid items-center gap-x-3 gap-y-1.5 border-b border-cursor-hairline-soft px-3 py-1.5 last:border-b-0 grid-cols-[minmax(11rem,0.5fr)_minmax(13rem,1fr)] ${isInvalid ? 'border-l-2 border-l-cursor-semantic-error bg-cursor-semantic-error/10' : isUnavailable ? 'bg-cursor-canvas-soft/70 border-l-2 border-l-cursor-hairline-strong' : 'bg-cursor-surface-card'}`}
                >
                  <div className="flex min-h-8 items-center">
                    <strong className={`font-medium text-xs leading-none ${isInvalid ? 'text-cursor-semantic-error' : isUnavailable ? 'text-cursor-muted' : 'text-cursor-ink'}`}>{stageLabel}</strong>
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
        );
      })()}
      {stageViolations.length > 0 && (
        <Alert severity="error" className="mt-2.5">
          <p className="m-0 font-semibold text-sm">Invalid tool combination</p>
          <ul className="m-0 mt-1 list-disc space-y-1 pl-4 text-sm">
            {stageViolations.map((violation) => {
              const stageLabel = metadata?.stages?.find((stage) => stage.id === violation.stageId)?.label;
              return (
                <li key={`${violation.stageId}:${violation.toolKey}`}>
                  {stageLabel ? `${stageLabel}: ` : ''}
                  {violation.reason}
                </li>
              );
            })}
          </ul>
        </Alert>
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

      {/* Invalid Preset File Popup */}
      {presetInvalid && (
        <ModalOverlay onClose={() => setPresetInvalid(false)}>
          <h3 className="m-0 mb-1.5 text-sm font-semibold leading-[1.3] text-cursor-semantic-error">
            Invalid preset file
          </h3>
          <p className="m-0 break-words text-xs leading-relaxed text-cursor-body">
            The selected file is not a valid preset file.
          </p>
          <div className="mt-3 flex items-center justify-end">
            <Button variant="primary" onClick={() => setPresetInvalid(false)}>
              OK
            </Button>
          </div>
        </ModalOverlay>
      )}
    </Panel>
  );
}

export function StatsAtlasSection() {
  const {data: metadata} = useMetadata();
  const formValues = usePipelineFormStore((s) => s.formValues);
  const selectedStatsAtlases = usePipelineFormStore((s) => s.selectedStatsAtlases);
  const setSelectedStatsAtlases = usePipelineFormStore((s) => s.setSelectedStatsAtlases);
  const setFormField = usePipelineFormStore((s) => s.setFormField);
  const order = ['subcortical_volume', 'cortical_volume', 'cortical_thickness'];

  const [atlasPickerStatKey, setAtlasPickerStatKey] = React.useState<string | null>(null);
  const [atlasSearch, setAtlasSearch] = React.useState('');

  const isCustomMode = formValues.pipelineMode === 'Custom';
  const stageStatsExtraction = formValues.stage_stats_extraction as string | undefined;
  const isStatsStageAvailable = Boolean(stageStatsExtraction && stageStatsExtraction.trim().length > 0);

  const removeAtlas = (statKey: string, atlasKey: string) => {
    const current = selectedStatsAtlases[statKey] || [];
    const nextList = current.filter((k) => k !== atlasKey);
    const nextMap = {...selectedStatsAtlases, [statKey]: nextList};
    setSelectedStatsAtlases(nextMap);

    if (formValues.pipelineMode && formValues.pipelineMode !== 'Custom') {
      const presetDefaults = metadata?.presets?.[formValues.pipelineMode]?.default_atlases?.[statKey] || [];
      if (presetDefaults.includes(atlasKey)) {
        setFormField('pipelineMode', 'Custom');
      }
    }
  };

  const addAtlas = (statKey: string, atlasKey: string) => {
    const current = selectedStatsAtlases[statKey] || [];
    if (!current.includes(atlasKey)) {
      const nextList = [...current, atlasKey];
      const nextMap = {...selectedStatsAtlases, [statKey]: nextList};
      setSelectedStatsAtlases(nextMap);

      if (formValues.pipelineMode && formValues.pipelineMode !== 'Custom') {
        const presetCovered = metadata?.presets?.[formValues.pipelineMode]?.stats || [];
        if (!presetCovered.includes(statKey)) {
          setFormField('pipelineMode', 'Custom');
        }
      }
    }
  };

  const toggleAtlas = (statKey: string, atlasKey: string) => {
    const current = selectedStatsAtlases[statKey] || [];
    if (current.includes(atlasKey)) {
      removeAtlas(statKey, atlasKey);
    } else {
      addAtlas(statKey, atlasKey);
    }
  };

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
          const showUnavailableWarning = isCustomMode && !isStatsStageAvailable && selectedAtlases.length > 0;

          return (
            <div key={statKey} className="py-2.5 first:pt-0 last:pb-0">
              <div className="grid grid-cols-[1fr_auto] items-center gap-x-2.5 gap-y-2">
                <div className="flex min-h-7 items-center gap-2">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-cursor-primary" />
                  <span className="text-sm font-semibold text-cursor-ink">
                    {statLabel} ({selectedAtlases.length})
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

                {showUnavailableWarning && (
                  <div className="col-span-2 mt-1">
                    <Alert severity="warning" size="sm">
                      This stats vector has selected atlases, but Statistics &amp; Atlas mapping is set to Not available.
                    </Alert>
                  </div>
                )}
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
          <ModalOverlay className="max-w-[42rem]" onClose={() => { setAtlasPickerStatKey(null); setAtlasSearch(''); }}>
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
              <div className="max-h-[30rem] space-y-1.5 overflow-y-auto pr-1">
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

export const NEUROFLOW_POLICIES = [
  { id: 'B0', label: 'Sequential FIFO', desc: 'Single-task sequential execution in strict arrival order (for resource-constrained machines).' },
  { id: 'B1', label: 'Parallel FIFO First-Fit', desc: 'Parallel execution using simple arrival-order queue; launches whichever task fits available resources.' },
  { id: 'B2', label: 'Shortest Processing Time First-Fit', desc: 'Prioritizes stages with shortest estimated runtime to minimize average waiting time.' },
  { id: 'B3', label: 'Static Critical-Path First-Fit', desc: 'Prioritizes tasks along the longest critical path based on static baseline estimates.' },
  { id: 'B4', label: 'Static Critical-Path Protected Backfill', desc: 'Critical-path priority with protected backfilling; allows non-critical tasks to backfill idle resources safely.' },
  { id: 'B5', label: 'Adaptive FIFO Resource Scheduler', desc: 'FIFO arrival-order queue combined with dynamic adaptive RAM and CPU resource scaling.' },
  { id: 'B6', label: 'Full NeuroFLOW', desc: 'Full adaptive scheduling: dynamic critical-path, starvation aging, intelligent backfill, and live resource learning (Recommended).' },
  { id: 'B7', label: 'HEFT Family', desc: 'Heterogeneous Earliest Finish Time (HEFT); optimizes stage assignment across mixed CPU and GPU devices.' },
] as const;

export function QueuePolicySelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (policyId: string) => void;
}) {
  const [isOpen, setIsOpen] = React.useState(false);
  const [hoveredId, setHoveredId] = React.useState<string | null>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);

  const selectedPolicy = NEUROFLOW_POLICIES.find((p) => p.id === value) || NEUROFLOW_POLICIES[6];
  const activeHoveredPolicy = NEUROFLOW_POLICIES.find((p) => p.id === hoveredId);

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setHoveredId(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative min-w-0">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`${inputCls} flex items-center justify-between text-left cursor-pointer transition-colors ${
          isOpen ? 'rounded-b-none border-b-transparent' : ''
        }`}
      >
        <span className="truncate text-sm font-normal text-cursor-ink">{selectedPolicy.label}</span>
        <ChevronDown className={`h-4 w-4 text-cursor-muted transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute left-0 top-full -mt-px w-full z-50">
          <div className="relative">
            {/* Options list seamlessly attached directly to the select button with bounded scrollable height */}
            <div className="w-full max-h-52 overflow-y-auto rounded-b-lg border border-cursor-hairline border-t-0 bg-cursor-surface-card p-1 shadow-xl backdrop-blur-md">
              {NEUROFLOW_POLICIES.map((p) => {
                const isSelected = p.id === value;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      onChange(p.id);
                      setIsOpen(false);
                      setHoveredId(null);
                    }}
                    onMouseEnter={() => setHoveredId(p.id)}
                    className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-sm text-left transition-colors cursor-pointer ${
                      isSelected
                        ? 'bg-cursor-primary/10 font-medium text-cursor-primary'
                        : 'text-cursor-ink hover:bg-cursor-canvas-soft'
                    }`}
                  >
                    <span>{p.label}</span>
                    {isSelected && <Check className="h-4 w-4 text-cursor-primary" />}
                  </button>
                );
              })}
            </div>

            {/* Instant Hover Preview Popover (positioned to the left to avoid split-pane clipping) */}
            {activeHoveredPolicy && (
              <div className="absolute right-[calc(100%+8px)] top-0 z-50 w-72 animate-in fade-in-50 zoom-in-95 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3.5 shadow-xl">
                <div className="text-sm font-semibold text-cursor-primary mb-1">
                  {activeHoveredPolicy.label}
                </div>
                <p className="text-xs leading-relaxed text-cursor-muted">
                  {activeHoveredPolicy.desc}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function AdvancedSettingsSection() {
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);
  const setFormFields = usePipelineFormStore((s) => s.setFormFields);
  const presetConfigInput = useRef<HTMLInputElement>(null);
  const profileConfigInput = useRef<HTMLInputElement>(null);
  const isCustomMode = formValues.pipelineMode === 'Custom';
  const hasCustomNeuroflowConfig = Boolean(
    String(formValues.neuroflowPresetFile || '').trim() && String(formValues.neuroflowProfileFile || '').trim(),
  );
  const neuroflowAvailable = !isCustomMode || hasCustomNeuroflowConfig;
  const neuroflowEnabled = formValues.neuroflowEnabled !== undefined ? Boolean(formValues.neuroflowEnabled) : true;
  const neuroflowWarmupEnabled = Boolean(formValues.neuroflowWarmupEnabled);
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  const neuroflowPresetId = NEUROFLOW_PIPELINE_CONFIGS[formValues.pipelineMode];
  const canShowAdvanced = isCustomMode || (neuroflowEnabled && neuroflowAvailable);

  const browseNeuroflowConfig = async (
    field: 'neuroflowPresetFile' | 'neuroflowProfileFile',
    inputRef: React.RefObject<HTMLInputElement | null>,
  ) => {
    if (!hasTauriInternals()) {
      inputRef.current?.click();
      return;
    }
    try {
      const selected = await open({
        multiple: false,
        filters: [{name: 'NeuroFLOW configuration', extensions: ['yaml', 'yml', 'json']}],
      });
      const path = selectedDialogPath(selected);
      if (path) setFormFields({pipelineMode: 'Custom', [field]: path});
    } catch {
      return;
    }
  };

  const currentPolicyId = String(formValues.neuroflowPolicy || 'B6');

  return (
    <Panel
      icon={<SlidersHorizontal className="h-4 w-4 text-cursor-primary" />}
      title="Advanced Settings"
      titleRight={
        canShowAdvanced ? (
          <Button
            variant="ghost"
            icon={showAdvanced ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            onClick={() => setShowAdvanced((prev) => !prev)}
          >
            {showAdvanced ? 'Hide Settings' : 'Show Settings'}
          </Button>
        ) : null
      }
      className="min-w-0"
    >
      <TooltipProvider>
        <div className="grid gap-3">
          <div>
            <label className={`flex cursor-pointer items-center gap-2 ${!neuroflowAvailable ? 'cursor-not-allowed' : ''}`}>
              <input
                type="checkbox"
                checked={neuroflowEnabled && neuroflowAvailable}
                disabled={!neuroflowAvailable}
                onChange={(e) => setFormField('neuroflowEnabled', e.target.checked)}
                className="h-4 w-4 accent-cursor-primary cursor-pointer disabled:cursor-not-allowed"
              />
              <span className="text-sm font-medium text-cursor-ink">Use NeuroFLOW scheduler</span>
              <InfoTooltip content="Optimizes multi-subject pipeline runs with adaptive concurrency, memory forecasting, and automatic fault recovery." />
            </label>
            {isCustomMode && !hasCustomNeuroflowConfig && (
              <p className="mt-2 text-xs text-cursor-muted">
                Select both a NeuroFLOW preset and profile configuration to enable the scheduler for a custom pipeline.
              </p>
            )}
          </div>

          {showAdvanced && canShowAdvanced && (
            <div className="grid gap-3">
              {/* Row 1: Max parallel tasks & Queue Policy */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-start">
                <label className={labelCls}>
                  <span className="flex items-center gap-1 font-medium text-cursor-ink">
                    <span>Max parallel tasks</span>
                    <InfoTooltip content="Maximum number of parallel pipeline stages running simultaneously across all subjects." />
                  </span>
                  <input
                    type="number"
                    min={1}
                    step={1}
                    value={formValues.neuroflowMaxConcurrentTasks ?? 2}
                    onChange={(e) => {
                      const maxConcurrent = Math.max(1, parseInt(e.target.value, 10) || 1);
                      setFormFields({
                        neuroflowMaxConcurrentTasks: maxConcurrent,
                        neuroflowWarmupInitialConcurrency: Math.min(
                          Number(formValues.neuroflowWarmupInitialConcurrency ?? 2),
                          maxConcurrent,
                        ),
                      });
                    }}
                    className={inputCls}
                  />
                  {Number(formValues.neuroflowMaxConcurrentTasks) === 1 && (
                    <span className="text-xs text-cursor-muted">
                      Loaded from workspace. Use 2 or more for parallel scheduling.
                    </span>
                  )}
                </label>

                <div className={labelCls}>
                  <span className="flex items-center gap-1 font-medium text-cursor-ink">
                    <span>Queue Policy</span>
                    <InfoTooltip content="Determines the task scheduling and queue prioritization strategy (B0 - B7)." />
                  </span>
                  <QueuePolicySelect
                    value={currentPolicyId}
                    onChange={(policyId) => setFormField('neuroflowPolicy', policyId)}
                  />
                </div>
              </div>

              {/* Row 2: Preset configuration & Profile configuration */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className={labelCls}>
                  <span className="flex items-center gap-1 font-medium text-cursor-ink">
                    <span>Preset configuration</span>
                    <InfoTooltip content="Path to the YAML file defining the pipeline directed acyclic graph (DAG) and stage dependencies." />
                  </span>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={formValues.neuroflowPresetFile ?? ''}
                      onChange={(e) => setFormFields({pipelineMode: 'Custom', neuroflowPresetFile: e.target.value})}
                      placeholder="Path to preset YAML/JSON"
                      className={`${inputCls} flex-1 min-w-0`}
                    />
                    <Button
                      variant="ghost"
                      icon={<FolderOpen className="h-3.5 w-3.5" />}
                      onClick={() => void browseNeuroflowConfig('neuroflowPresetFile', presetConfigInput)}
                    >
                      Browse
                    </Button>
                    <input ref={presetConfigInput} className="hidden" type="file" accept=".yaml,.yml,.json" />
                  </div>
                </label>

                <label className={labelCls}>
                  <span className="flex items-center gap-1 font-medium text-cursor-ink">
                    <span>Profile configuration</span>
                    <InfoTooltip content="Path to the YAML file containing cold-start resource priors (RAM, CPU, and runtime benchmarks)." />
                  </span>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={formValues.neuroflowProfileFile ?? ''}
                      onChange={(e) => setFormFields({pipelineMode: 'Custom', neuroflowProfileFile: e.target.value})}
                      placeholder="Path to profile YAML/JSON"
                      className={`${inputCls} flex-1 min-w-0`}
                    />
                    <Button
                      variant="ghost"
                      icon={<FolderOpen className="h-3.5 w-3.5" />}
                      onClick={() => void browseNeuroflowConfig('neuroflowProfileFile', profileConfigInput)}
                    >
                      Browse
                    </Button>
                    <input ref={profileConfigInput} className="hidden" type="file" accept=".yaml,.yml,.json" />
                  </div>
                </label>
              </div>

              {/* Row 3: Warm-up checkbox */}
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={neuroflowWarmupEnabled}
                  onChange={(e) => setFormField('neuroflowWarmupEnabled', e.target.checked)}
                  className="h-3.5 w-3.5 accent-cursor-primary cursor-pointer"
                />
                <span className="text-xs font-medium text-cursor-ink">Start safely, then scale up</span>
                <InfoTooltip content="Warm-up mode: starts execution conservatively with 1 slot, then automatically scales up concurrency after initial stages complete stably." />
              </label>
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

function ModalOverlay({
  onClose,
  children,
  className = 'max-w-[32rem]',
}: {
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/35 p-3"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={`relative w-full rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 shadow-none ${className}`}>
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
  remotePayload: RemotePayload;
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
          <div className="px-4 py-3">
            <Alert severity="error" size="sm">{statusMsg}</Alert>
          </div>
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
  initialSelectedPaths,
}: {
  inputSource: string;
  inputPath: string;
  currentCount: number | undefined;
  onConfirm: (count: number, paths?: string[]) => void;
  onClose: () => void;
  localFileListLen: number;
  isConnected: boolean;
  remotePayload: Record<string, unknown> | RemotePayload;
  cacheKey: string;
  batchScanCache: BatchScanCache | null;
  setBatchScanCache: React.Dispatch<React.SetStateAction<BatchScanCache | null>>;
  initialSelectedPaths?: string[] | undefined;
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
    cacheMatches
      ? new Set(batchScanCache!.selectedPaths)
      : new Set(initialSelectedPaths ?? []),
  );
  const [scanStatus, setScanStatus] = React.useState(cacheMatches ? batchScanCache!.status : '');
  const [scanMode, setScanMode] = React.useState<ScanMode>(cacheMatches ? batchScanCache!.scanMode : 'recursive');
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

        // Auto-select: prioritize initialSelectedPaths if provided, otherwise all candidates with unique subject_label
        const initialSet = new Set(initialSelectedPaths?.map((p) => p.trim()).filter(Boolean) ?? []);
        const autoSelected = new Set<string>();
        if (initialSet.size > 0) {
          for (const e of candidates) {
            if (
              initialSet.has(e.path) ||
              initialSet.has(e.name) ||
              Array.from(initialSet).some((p) => p.endsWith(e.path) || e.path.endsWith(p))
            ) {
              autoSelected.add(e.path);
            }
          }
        }

        const labelCounts = new Map<string, number>();
        for (const e of candidates) {
          const lbl = e.subject_label ?? e.name;
          labelCounts.set(lbl, (labelCounts.get(lbl) ?? 0) + 1);
        }

        if (autoSelected.size === 0) {
          for (const e of candidates) {
            const lbl = e.subject_label ?? e.name;
            if ((labelCounts.get(lbl) ?? 0) === 1) {
              autoSelected.add(e.path);
            }
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
  disabled = false,
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
  disabled?: boolean;
}) {
  return (
    <label className={`${labelCls} ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}>
      {label}
      <div className="flex gap-1.5">
        <input
          id={id}
          name={id}
          value={value}
          placeholder={disabled ? 'Connect to server first' : placeholder}
          required={required && !disabled}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className={`${inputCls} flex-1 ${disabled ? 'cursor-not-allowed bg-cursor-canvas-soft text-cursor-muted border-cursor-hairline-soft' : ''}`}
        />
        <button
          type="button"
          onClick={onBrowse}
          title={disabled ? 'Connect to server first' : browseLabel}
          disabled={disabled}
          className="inline-flex h-8 flex-none cursor-pointer items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card px-2.5 text-xs font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-50"
        >
          {browseLabel}
        </button>
        {secondaryBrowse && (
          <button
            type="button"
            onClick={secondaryBrowse.onClick}
            title={disabled ? 'Connect to server first' : (secondaryBrowse.title ?? secondaryBrowse.label)}
            disabled={disabled}
            className="inline-flex h-8 flex-none cursor-pointer items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card px-2.5 text-xs font-medium text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-50"
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
  options: {label: string; value: string; hint?: string; disabled?: boolean}[];
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      {options.map((opt) => {
        const itemDisabled = disabled || opt.disabled;
        return (
          <label
            key={opt.value}
            className={`flex items-start gap-2 rounded-md border px-2.5 py-1.5 transition-colors ${
              value === opt.value
                ? 'border-cursor-primary bg-cursor-canvas-soft'
                : 'border-cursor-hairline bg-cursor-surface-card hover:border-cursor-hairline-strong'
            } ${itemDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
          >
            <input
              type="radio"
              name={name}
              value={opt.value}
              checked={value === opt.value}
              disabled={itemDisabled}
              onChange={() => !itemDisabled && onChange(opt.value)}
              className="mt-0.5 h-3.5 w-3.5 flex-none accent-cursor-primary"
            />
            <span className="grid gap-0.25">
              <span className="text-sm font-medium leading-[1.3] text-cursor-ink">{opt.label}</span>
              {opt.hint && <span className="text-xs leading-[1.3] text-cursor-muted">{opt.hint}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// InputOutputSection — main export
// ---------------------------------------------------------------------------

export function InputOutputSection() {
  const client = useClient();
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);
  const setFormFields = usePipelineFormStore((s) => s.setFormFields);

  // Remote connection state
  const remoteConnected = useRemoteStore((s) => s.connected);
  const remotePayload = buildRemotePayload(formValues);

  // Derived helpers
  const isLocal = formValues.runtimeTarget === 'Local';
  const inputSource = formValues.inputSource as string;
  const isBatch = formValues.inputMode === 'batch_folder';
  const isServerSource = inputSource === 'Server';

  // Manual staging upload state
  const [uploadingStaging, setUploadingStaging] = React.useState(false);
  const [uploadStatus, setUploadStatus] = React.useState<{type: 'info' | 'success' | 'error'; message: string} | null>(null);

  const handleManualUploadToServer = async () => {
    if (!remoteConnected || !formValues.inputPath || !formValues.inputServerDir) return;
    setUploadingStaging(true);
    setUploadStatus({type: 'info', message: 'Uploading to server...'});
    try {
      const res = await client.uploadStage({
        ...remotePayload,
        local_path: formValues.inputPath,
        remote_path: formValues.inputServerDir,
      });
      if (res.ok) {
        setUploadStatus({type: 'success', message: 'Data uploaded successfully.'});
      } else {
        setUploadStatus({type: 'error', message: res.error || 'Upload failed.'});
      }
    } catch (err: unknown) {
      setUploadStatus({type: 'error', message: err instanceof Error ? err.message : 'Upload failed.'});
    } finally {
      setUploadingStaging(false);
    }
  };

  // Modal states
  const [dualPaneModal, setDualPaneModal] = React.useState(false);
  const [serverInputModal, setServerInputModal] = React.useState(false);
  const [serverStagingModal, setServerStagingModal] = React.useState(false);
  const [serverOutputModal, setServerOutputModal] = React.useState(false);
  const [batchModal, setBatchModal] = React.useState(false);

  // Batch scan cache — persists across modal open/close
  const [batchScanCache, setBatchScanCache] = React.useState<BatchScanCache | null>(null);
  const batchCacheKey = `${inputSource}|${formValues.inputPath}|${formValues.inputServerDir || ''}|${JSON.stringify(remotePayload)}`;

  // Invalidate cache when inputs change
  React.useEffect(() => {
    setBatchScanCache((prev) => (prev && prev.cacheKey !== batchCacheKey ? null : prev));
  }, [batchCacheKey]);

  // Ref for hidden local file input (browser fallback for directory browse)
  const localInputRef = React.useRef<HTMLInputElement | null>(null);
  const [localFileListLen, setLocalFileListLen] = React.useState(0);

  // When runtime is Local or remote is disconnected, force source to Local
  React.useEffect(() => {
    if ((isLocal || !remoteConnected) && inputSource === 'Server') {
      setFormField('inputSource', 'Local');
    }
  }, [isLocal, remoteConnected, inputSource, setFormField]);

  // Input Mode radio options — map to existing backend inputMode values
  const inputModeOptions = [
    {label: 'Single input', value: 'file', hint: 'Process one NIfTI file or DICOM series folder.'},
    {label: 'Batch input', value: 'batch_folder', hint: 'Process a folder of images or DICOM series.'},
  ];

  // Source radio options
  const sourceOptions = [
    {
      label: 'Local',
      value: 'Local',
      hint: 'Files on this machine.',
      disabled: false,
    },
    {
      label: 'Server',
      value: 'Server',
      hint: isLocal
        ? 'Available when Runtime target is Server.'
        : !remoteConnected
          ? 'Connect to server first.'
          : 'Files on the remote server.',
      disabled: isLocal || !remoteConnected,
    },
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
              />
              {!isLocal && (
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    icon={<Upload className="h-3.5 w-3.5" />}
                    onClick={() => setDualPaneModal(true)}
                    disabled={!remoteConnected}
                  >
                    Upload data to server
                  </Button>
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

          {/* Row 2: Path fields — Local target, or Server target with lazy upload */}
          {inputSource === 'Local' && !isLocal && (
            <div className="grid gap-3">
              {isBatch ? (
                <PathField
                  id="inputPath"
                  label="Input location (local)"
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
                  label="Input location (local)"
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
              <PathField
                id="inputServerDir"
                label="Input location (server)"
                value={formValues.inputServerDir || ''}
                placeholder="~/mri-uploads"
                onChange={(v) => setFormField('inputServerDir', v)}
                onBrowse={() => setServerStagingModal(true)}
                disabled={!remoteConnected}
                required
              />
              <PathField
                id="serverOutputDir"
                label="Output location (server)"
                value={formValues.serverOutputDir || ''}
                placeholder="/home/user/mri-outputs"
                onChange={(v) => setFormField('serverOutputDir', v)}
                onBrowse={() => setServerOutputModal(true)}
                disabled={!remoteConnected}
                required
              />
            </div>
          )}

          {/* Row 2: Path fields — Local */}
          {inputSource === 'Local' && isLocal && (
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
                disabled={!remoteConnected}
                required
              />
              <PathField
                id="serverOutputDir"
                label="Output location (server path)"
                value={formValues.serverOutputDir || ''}
                placeholder="/home/user/mri-outputs"
                onChange={(v) => setFormField('serverOutputDir', v)}
                onBrowse={() => setServerOutputModal(true)}
                disabled={!remoteConnected}
                required
              />
            </div>
          )}

        </div>
      </Panel>

      {/* Server staging browse modal (lazy-upload inputs root) */}
      {serverStagingModal && (
        remoteConnected ? (
          <ServerBrowserModal
            title="Browse server - Input staging location"
            initialPath={formValues.inputServerDir || '~'}
            remotePayload={remotePayload}
            selectMode="path"
            onConfirm={(p) => {
              setFormField('inputServerDir', p);
              setServerStagingModal(false);
            }}
            onClose={() => setServerStagingModal(false)}
          />
        ) : (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-3"
            onMouseDown={() => setServerStagingModal(false)}
          >
            <div className="rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 max-w-sm w-full">
              <h3 className="m-0 mb-2 text-sm font-semibold text-cursor-ink">SSH not connected</h3>
              <p className="text-xs text-cursor-muted">Connect in the SSH Server card first, then browse.</p>
              <div className="mt-3 flex justify-end">
                <Button variant="ghost" onClick={() => setServerStagingModal(false)}>Close</Button>
              </div>
            </div>
          </div>
        )
      )}

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
            initialPath={formValues.serverOutputDir || '~'}
            remotePayload={remotePayload}
            selectMode="path"
            onConfirm={(p) => {
              setFormField('serverOutputDir', p);
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
          initialSelectedPaths={
            formValues.additionalInputPaths
              ? formValues.additionalInputPaths.split(',').map((s) => s.trim()).filter(Boolean)
              : undefined
          }
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

      {/* Dual-Pane File Transfer Modal */}
      {dualPaneModal && (
        <DualPaneTransferModal
          onClose={() => setDualPaneModal(false)}
          remotePayload={remotePayload}
          initialLocalPath={formValues.inputPath || ''}
          initialRemotePath={formValues.inputServerDir || formValues.inputPath || '~'}
          onSetInputLocation={(path) => {
            if (inputSource === 'Local') {
              setFormField('inputServerDir', path);
            } else {
              setFormField('inputPath', path);
            }
          }}
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

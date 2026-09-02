import React, {useRef} from 'react';
import {toast} from 'sonner';
import {
  Workflow, FolderInput, FolderOpen, Folder, FolderUp, FolderPlus, Save, Play, Square, Loader2, FileKey, Upload,
  SlidersHorizontal, Eye, EyeOff, Layers, Plus, Check, X, Search, BarChart3, Zap, RefreshCw, Gauge,
  HardDrive, Cpu, Info, ListOrdered, ChevronDown, FileText, Server, ArrowRight, ArrowUp
} from 'lucide-react';
import {open} from '@tauri-apps/plugin-dialog';
import {useNavigate} from 'react-router';
import {Panel, Button, Alert, CustomSelect, inputCls, labelCls} from '../components/ui';
import {EMPTY_STAGE_VIOLATIONS, validateStageTools} from '../lib/stageValidation';
import {Tooltip, TooltipTrigger, TooltipContent, TooltipProvider} from '@/components/ui/tooltip';
import {SplitPaneForm} from '../components/SplitPaneForm';
import {RuntimeSection} from '../components/RuntimeSection';
import {StartPipelineDialog} from '../components/StartPipelineDialog';
import {DualPaneTransferModal} from '../components/DualPaneTransferModal';
import {useStartPipelineStream} from '../hooks/useStartPipelineStream';
import {useMetadata, useClient, useEnvironment} from '../query/useEnvironment';
import {useRemoteBrowseMutation, useLocalBrowseMutation, useRemoteMkdirMutation} from '../query/useRemote';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useJobsStore} from '../stores/jobsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {buildRunConfig, buildRemotePayload, NEUROFLOW_PIPELINE_CONFIGS, neuroflowConfigFilesForMode, type RemotePayload} from '../api/runConfig';
import {presetDefaultAtlases} from '../lib/pipelinePresets';
import {buildPresetPayload, defaultConfigName, saveJsonAsDialog} from '../lib/configExport';
import {currentTargetHardware} from '../lib/runtime';
import {normalizeJob, sortJobsByStartedAtDesc} from '../jobFormatters';
import type {RemoteBrowseEntry, RemoteBrowseResponse} from '../types/backend';


function browseJsonFile(inputRef: React.RefObject<HTMLInputElement | null>) {
  if (inputRef.current) inputRef.current.click();
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
      toast.success('Preset saved successfully');
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
      toast.success('Preset loaded successfully');
    } catch {
      setPresetInvalid(true);
    }
  }

  return (
    <Panel
      icon={<Workflow className="h-4 w-4 text-cursor-primary" />}
      title="Pipeline Steps"
      className="min-w-0"
    >
      <div className="mb-2.5 flex flex-col sm:flex-row sm:items-end gap-2">
        <label className={`${labelCls} flex-1 min-w-0`}>
          Pipeline preset
          <CustomSelect
            id="pipelineMode"
            name="pipelineMode"
            value={formValues.pipelineMode}
            onChange={(val) => handlePipelineModeChange(val)}
            options={(metadata?.pipeline_modes || []).map((mode) => ({
              value: mode.id,
              label: mode.id,
            }))}
          />
        </label>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 pb-0.5">
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
          <div className="grid border border-cursor-hairline rounded-md">
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
                  <CustomSelect
                    name={`stage_${stage.id}`}
                    value={selectedToolKey}
                    onChange={(val) => handleStageToolChange(stage.id, val)}
                    options={[
                      {value: '', label: 'Not available'},
                      ...tools.map((toolKey) => {
                        const tool = metadata?.tools?.[toolKey];
                        return {
                          value: toolKey,
                          label: tool?.display_name || toolKey,
                        };
                      }),
                    ]}
                  />
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
              readOnly
              placeholder="Select license.txt via Browse"
              className={`${inputCls} bg-cursor-canvas-soft text-cursor-muted`}
            />
          </label>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              variant="ghost"
              icon={<FolderOpen className="h-3.5 w-3.5" />}
              onClick={async () => {
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
              Browse
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
  { id: 'B6', label: 'Full NeuroFLOW (default)', desc: 'Uses the complete optimizer described in the NeuroFLOW optimizer design document.' },
  { id: 'B0', label: 'Sequential FIFO', desc: 'One task at a time; first-ready, first-added; static profiles; no adaptation; no backfilling.' },
  { id: 'B1', label: 'Parallel FIFO First-Fit', desc: 'Insertion-order ready queue; first feasible configuration; static profiles; no critical-path ranking; no protected backfilling.' },
  { id: 'B2', label: 'Shortest Processing Time First-Fit', desc: 'Tasks are ordered by ascending estimated runtime; uses static profiles and no protected backfilling.' },
  { id: 'B3', label: 'Static Critical-Path First-Fit', desc: 'Upward critical-path rank; static profiles; no adaptation; no aging; no protected backfilling.' },
  { id: 'B4', label: 'Static Critical-Path Protected Backfill', desc: 'Upward critical-path rank; static profiles; protected backfilling; CPU/GPU configuration selection; no adaptive estimates.' },
  { id: 'B5', label: 'Adaptive FIFO Resource Scheduler', desc: 'NeuroFLOW adaptive estimators; FIFO priority; adaptive concurrency; no critical-path ranking.' },
] as const;

export function QueuePolicySelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (policyId: string) => void;
}) {
  return (
    <CustomSelect
      value={value}
      onChange={onChange}
      showHoverPreview={true}
      previewPosition="left"
      options={NEUROFLOW_POLICIES.map((p) => ({
        value: p.id,
        label: p.label,
        description: p.desc,
      }))}
    />
  );
}

export function AdvancedSettingsSection() {
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);
  const setFormFields = usePipelineFormStore((s) => s.setFormFields);
  const environment = useEnvironment().data;
  const remoteResult = useRemoteStore();
  const hardware = currentTargetHardware({
    runtimeTarget: formValues.runtimeTarget,
    environment,
    remoteResult,
  });
  const client = useClient();
  const maxTaskCap = hardware.logicalCores || 32;
  const isCustomMode = formValues.pipelineMode === 'Custom';
  const hasCustomNeuroflowConfig = Boolean(
    String(formValues.neuroflowPresetFile || '').trim() && String(formValues.neuroflowProfileFile || '').trim(),
  );
  const neuroflowAvailable = !isCustomMode || hasCustomNeuroflowConfig;
  const neuroflowEnabled = formValues.neuroflowEnabled !== undefined ? Boolean(formValues.neuroflowEnabled) : true;
  const neuroflowWarmupEnabled = Boolean(formValues.neuroflowWarmupEnabled);
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  const [presetInvalid, setPresetInvalid] = React.useState(false);
  const [profileInvalid, setProfileInvalid] = React.useState(false);
  const neuroflowPresetId = NEUROFLOW_PIPELINE_CONFIGS[formValues.pipelineMode];
  const canShowAdvanced = isCustomMode || (neuroflowEnabled && neuroflowAvailable);

  const browseNeuroflowConfig = async (
    field: 'neuroflowPresetFile' | 'neuroflowProfileFile',
  ) => {
    const kind = field === 'neuroflowPresetFile' ? 'preset' : 'profile';
    try {
      const selected = await open({
        multiple: false,
        filters: [{name: 'NeuroFLOW configuration', extensions: ['yaml', 'yml', 'json']}],
      });
      const path = selectedDialogPath(selected);
      if (!path) return;
      const res = await client.validateNeuroflowConfig({path, kind});
      if (res.ok) {
        setFormFields({pipelineMode: 'Custom', [field]: path});
      } else {
        if (kind === 'preset') setPresetInvalid(true);
        else setProfileInvalid(true);
      }
    } catch {
      if (kind === 'preset') setPresetInvalid(true);
      else setProfileInvalid(true);
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
                  <span className="flex items-center justify-between">
                    <span className="flex items-center gap-1 font-medium text-cursor-ink">
                      <span>Max parallel tasks</span>
                      <InfoTooltip content="Maximum number of parallel pipeline stages running simultaneously across all subjects." />
                    </span>
                    <span className="text-2xs font-normal text-cursor-muted">
                      {hardware.logicalCores ? `Max: ${hardware.logicalCores} cores` : '—'}
                    </span>
                  </span>
                  <input
                    type="number"
                    min={1}
                    max={maxTaskCap}
                    step={1}
                    value={formValues.neuroflowMaxConcurrentTasks ?? 2}
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10);
                      const maxConcurrent = isNaN(val) ? 1 : Math.max(1, Math.min(maxTaskCap, val));
                      setFormFields({
                        neuroflowMaxConcurrentTasks: maxConcurrent,
                        neuroflowWarmupInitialConcurrency: Math.min(
                          Number(formValues.neuroflowWarmupInitialConcurrency ?? 2),
                          maxConcurrent,
                        ),
                      });
                    }}
                    onBlur={() => {
                      const current = Number(formValues.neuroflowMaxConcurrentTasks) || 2;
                      const clamped = Math.max(1, Math.min(maxTaskCap, current));
                      if (clamped !== formValues.neuroflowMaxConcurrentTasks) {
                        setFormField('neuroflowMaxConcurrentTasks', clamped);
                      }
                    }}
                    className={inputCls}
                  />
                </label>

                <div className="flex flex-col gap-1">
                  <span className="flex items-center gap-1 font-medium text-cursor-ink text-xs">
                    <span>Queue Policy</span>
                    <InfoTooltip content="Defines task-dispatch order and concurrent-schedule behavior across pipeline stages." />
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
                      readOnly
                      placeholder="Select preset YAML/JSON via Browse"
                      className={`${inputCls} flex-1 min-w-0 bg-cursor-canvas-soft text-cursor-muted`}
                    />
                    <Button
                      variant="ghost"
                      icon={<FolderOpen className="h-3.5 w-3.5" />}
                      aria-label="Browse preset configuration"
                      onClick={() => void browseNeuroflowConfig('neuroflowPresetFile')}
                    >
                      Browse
                    </Button>
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
                      readOnly
                      placeholder="Select profile YAML/JSON via Browse"
                      className={`${inputCls} flex-1 min-w-0 bg-cursor-canvas-soft text-cursor-muted`}
                    />
                    <Button
                      variant="ghost"
                      icon={<FolderOpen className="h-3.5 w-3.5" />}
                      aria-label="Browse profile configuration"
                      onClick={() => void browseNeuroflowConfig('neuroflowProfileFile')}
                    >
                      Browse
                    </Button>
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

      {/* Invalid NeuroFLOW Preset File Popup */}
      {presetInvalid && (
        <ModalOverlay onClose={() => setPresetInvalid(false)} className="max-w-[24rem]">
          <h3 className="m-0 mb-1.5 text-sm font-semibold leading-[1.3] text-cursor-semantic-error">
            Invalid preset file
          </h3>
          <p className="m-0 break-words text-xs leading-relaxed text-cursor-body">
            The selected file is not a valid NeuroFLOW preset configuration.
          </p>
          <div className="mt-3 flex items-center justify-end">
            <Button variant="primary" onClick={() => setPresetInvalid(false)}>
              OK
            </Button>
          </div>
        </ModalOverlay>
      )}

      {/* Invalid NeuroFLOW Profile File Popup */}
      {profileInvalid && (
        <ModalOverlay onClose={() => setProfileInvalid(false)} className="max-w-[24rem]">
          <h3 className="m-0 mb-1.5 text-sm font-semibold leading-[1.3] text-cursor-semantic-error">
            Invalid profile file
          </h3>
          <p className="m-0 break-words text-xs leading-relaxed text-cursor-body">
            The selected file is not a valid NeuroFLOW profile configuration.
          </p>
          <div className="mt-3 flex items-center justify-end">
            <Button variant="primary" onClick={() => setProfileInvalid(false)}>
              OK
            </Button>
          </div>
        </ModalOverlay>
      )}
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
      <div className="relative my-auto w-full max-w-[min(52rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-cursor-hairline bg-cursor-surface-card shadow-none">
        {children}
      </div>
    </div>
  );
}

function ServerBrowserModal({
  title,
  initialPath,
  remotePayload,
  foldersOnly = false,
  onConfirm,
  onClose,
}: {
  title: string;
  initialPath: string;
  remotePayload: RemotePayload;
  foldersOnly?: boolean;
  onConfirm: (path: string) => void;
  onClose: () => void;
}) {
  const browseMutation = useRemoteBrowseMutation();
  const mkdirMutation = useRemoteMkdirMutation();
  const [currentPath, setCurrentPath] = React.useState(initialPath || '~');
  const [entries, setEntries] = React.useState<RemoteBrowseEntry[]>([]);
  const [parentPath, setParentPath] = React.useState('~');
  const [statusMsg, setStatusMsg] = React.useState('');
  const [isError, setIsError] = React.useState(false);
  const [manualPath, setManualPath] = React.useState(initialPath || '');
  const [searchQuery, setSearchQuery] = React.useState('');
  const [selectedEntryPath, setSelectedEntryPath] = React.useState<string | null>(null);

  // New folder creation state
  const [isCreatingFolder, setIsCreatingFolder] = React.useState(false);
  const [newFolderName, setNewFolderName] = React.useState('');
  const [newFolderError, setNewFolderError] = React.useState<string | null>(null);
  const newFolderInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (isCreatingFolder) {
      newFolderInputRef.current?.focus();
    }
  }, [isCreatingFolder]);

  const cleanTitle = React.useMemo(() => {
    return title.replace(/^Browse server\s*[-–—:]\s*/i, '').trim() || title;
  }, [title]);

  const doBrowse = React.useCallback(
    (path: string) => {
      setStatusMsg('Loading...');
      setIsError(false);
      setSelectedEntryPath(null);
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
            const resolvedPath = res.path ?? path;
            setCurrentPath(resolvedPath);
            setManualPath(resolvedPath);
            setParentPath(res.parent ?? resolvedPath);
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

  const handleCreateFolder = () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) {
      setNewFolderError('Folder name is required');
      return;
    }
    if (trimmed.includes('/') || trimmed.includes('\\')) {
      setNewFolderError('Folder name cannot contain path separators');
      return;
    }
    const base = currentPath.replace(/\/+$/, '') || '/';
    const targetPath = base === '/' ? `/${trimmed}` : `${base}/${trimmed}`;
    setNewFolderError(null);

    mkdirMutation.mutate(
      {
        ...remotePayload,
        path: targetPath,
      },
      {
        onSuccess: (res) => {
          if (res.ok) {
            setIsCreatingFolder(false);
            setNewFolderName('');
            setNewFolderError(null);
            setSelectedEntryPath(targetPath);
            setManualPath(targetPath);
            toast.success(`Created folder "${trimmed}"`);
            doBrowse(currentPath);
          } else {
            setNewFolderError(res.error || 'Failed to create folder');
          }
        },
        onError: (err: unknown) => {
          setNewFolderError(err instanceof Error ? err.message : 'Failed to create folder');
        },
      },
    );
  };

  const filteredEntries = React.useMemo(() => {
    const list = foldersOnly ? entries.filter((e) => e.kind === 'directory') : entries;
    if (!searchQuery.trim()) return list;
    const q = searchQuery.toLowerCase().trim();
    return list.filter((e) => e.name.toLowerCase().includes(q));
  }, [entries, searchQuery, foldersOnly]);

  const dirs = filteredEntries.filter((e) => e.kind === 'directory');
  const files = foldersOnly ? [] : filteredEntries.filter((e) => e.kind === 'file');
  const isLoading = browseMutation.isPending;

  // Selected item name for footer context
  const selectedItemName = React.useMemo(() => {
    if (!selectedEntryPath) return null;
    const parts = selectedEntryPath.replace(/\\/g, '/').split('/').filter(Boolean);
    return parts[parts.length - 1] || selectedEntryPath;
  }, [selectedEntryPath]);

  const targetPathToConfirm = selectedEntryPath || manualPath || currentPath;

  const confirmBtnLabel = React.useMemo(() => {
    if (foldersOnly) return 'Select folder';
    if (selectedEntryPath) {
      const isFile = files.some((f) => f.path === selectedEntryPath);
      if (isFile) return 'Select file';
    }
    return 'Select folder';
  }, [foldersOnly, selectedEntryPath, files]);

  return (
    <WideModalOverlay onClose={onClose}>
      {/* Header */}
      <div className="border-b border-cursor-hairline px-4 py-3">
        <div className="mb-2.5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-cursor-primary/10 text-cursor-primary">
              <Server className="h-4 w-4" />
            </span>
            <h3 className="m-0 text-base font-semibold text-cursor-ink">{cleanTitle}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-cursor-muted transition-colors hover:bg-cursor-canvas-soft hover:text-cursor-ink"
            aria-label="Close"
          >
            <X className="h-4.5 w-4.5" />
          </button>
        </div>

        {/* Path bar & Action buttons: [Input] [Go ->] [Up ^] [Reload] [New Folder] */}
        <div className="flex items-center gap-1.5">
          <div className="relative min-w-0 flex-1">
            <input
              className={`${inputCls} w-full font-mono text-sm`}
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') doBrowse(manualPath);
              }}
              placeholder="/home/user/mri-data"
              aria-label="Remote path"
            />
          </div>
          <button
            type="button"
            onClick={() => doBrowse(manualPath)}
            disabled={isLoading}
            title="Go to path"
            aria-label="Go"
            className="inline-flex h-8.5 w-8.5 flex-none items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => doBrowse(parentPath)}
            disabled={parentPath === currentPath || isLoading}
            title={parentPath !== currentPath ? `Parent directory: ${parentPath}` : 'At root directory'}
            aria-label="Parent directory"
            className="inline-flex h-8.5 w-8.5 flex-none items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => doBrowse(currentPath)}
            disabled={isLoading}
            title="Refresh directory"
            aria-label="Refresh directory"
            className="inline-flex h-8.5 w-8.5 flex-none items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft disabled:cursor-not-allowed disabled:opacity-40"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => {
              setIsCreatingFolder((v) => !v);
              setNewFolderName('');
              setNewFolderError(null);
            }}
            disabled={isLoading || mkdirMutation.isPending}
            title="Create new folder"
            aria-label="Create new folder"
            className={`inline-flex h-8.5 w-8.5 flex-none items-center justify-center rounded-md border transition-colors ${
              isCreatingFolder
                ? 'border-cursor-primary bg-cursor-primary/10 text-cursor-primary'
                : 'border-cursor-hairline bg-cursor-surface-card text-cursor-ink hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft'
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            <FolderPlus className="h-4 w-4" />
          </button>
        </div>

        {/* Create New Folder Inline Row */}
        {isCreatingFolder && (
          <div className="mt-2 flex flex-col gap-1 rounded-md border border-cursor-primary/30 bg-cursor-primary/5 p-2">
            <div className="flex items-center gap-2">
              <FolderPlus className="h-4.5 w-4.5 flex-none text-cursor-primary" />
              <input
                ref={newFolderInputRef}
                type="text"
                value={newFolderName}
                onChange={(e) => {
                  setNewFolderName(e.target.value);
                  if (newFolderError) setNewFolderError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateFolder();
                  if (e.key === 'Escape') {
                    setIsCreatingFolder(false);
                    setNewFolderName('');
                    setNewFolderError(null);
                  }
                }}
                placeholder="New folder name..."
                className="h-8 min-w-0 flex-1 rounded border border-cursor-hairline bg-cursor-surface-card px-2.5 text-sm text-cursor-ink outline-none placeholder:text-cursor-muted focus:border-cursor-primary"
              />
              <button
                type="button"
                onClick={handleCreateFolder}
                disabled={mkdirMutation.isPending || !newFolderName.trim()}
                className="inline-flex h-8 items-center gap-1 rounded bg-cursor-primary px-3 text-xs font-medium text-white transition-colors hover:bg-cursor-primary-hover disabled:opacity-50 cursor-pointer"
              >
                {mkdirMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                <span>Create</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsCreatingFolder(false);
                  setNewFolderName('');
                  setNewFolderError(null);
                }}
                className="inline-flex h-8 w-8 items-center justify-center rounded text-cursor-muted hover:bg-cursor-canvas-soft hover:text-cursor-ink cursor-pointer"
                aria-label="Cancel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {newFolderError && (
              <div className="text-xs font-medium text-red-500 pl-6.5">
                {newFolderError}
              </div>
            )}
          </div>
        )}

        {/* Filter bar */}
        {entries.length > 0 && (
          <div className="relative mt-2">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-cursor-muted" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={foldersOnly ? "Filter folders..." : "Filter files and folders..."}
              className="h-8.5 w-full rounded-md border border-cursor-hairline bg-cursor-canvas-soft pl-9 pr-8 text-sm text-cursor-ink outline-none placeholder:text-cursor-muted focus:border-cursor-hairline-strong focus:bg-cursor-surface-card"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-cursor-muted hover:text-cursor-ink"
                aria-label="Clear filter"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* Entry list */}
      <div className="max-h-[min(26rem,55vh)] overflow-y-auto bg-cursor-canvas-soft">
        {/* Up row */}
        {parentPath !== currentPath && !isLoading && !searchQuery && (
          <button
            type="button"
            onClick={() => doBrowse(parentPath)}
            className="flex w-full items-center gap-2.5 border-b border-cursor-hairline-soft px-4 py-2.5 text-left text-sm text-cursor-muted transition-colors hover:bg-cursor-surface-card hover:text-cursor-ink"
          >
            <ArrowUp className="h-4.5 w-4.5 flex-none text-cursor-primary/70" />
            <span className="text-sm font-normal">.. (Parent directory)</span>
          </button>
        )}

        {/* Loading with spinner icon */}
        {isLoading && (
          <div className="flex flex-col items-center justify-center gap-2.5 py-12 text-sm text-cursor-muted">
            <Loader2 className="h-5 w-5 animate-spin text-cursor-primary" />
            <span>Loading directory...</span>
          </div>
        )}

        {/* Error */}
        {!isLoading && isError && statusMsg && (
          <div className="px-4 py-3">
            <Alert severity="error" size="sm">{statusMsg}</Alert>
          </div>
        )}

        {/* Empty directory */}
        {!isLoading && !isError && entries.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-sm text-cursor-muted">
            <FolderOpen className="h-8 w-8 stroke-[1.5] text-cursor-muted/40" />
            <span>This directory is empty.</span>
          </div>
        )}

        {/* Filter no results */}
        {!isLoading && !isError && entries.length > 0 && filteredEntries.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-1.5 py-8 text-sm text-cursor-muted">
            <Search className="h-6 w-6 stroke-[1.5] text-cursor-muted/40" />
            <span>No matching {foldersOnly ? 'folders' : 'items'} found</span>
          </div>
        )}

        {/* Directories */}
        {!isLoading &&
          dirs.map((entry) => {
            const isDcm = entry.is_dicom_series;
            const isSelected = selectedEntryPath === entry.path;
            return (
              <button
                key={entry.path}
                type="button"
                title={`${entry.name} (Double-click to open)`}
                onClick={() => {
                  setSelectedEntryPath(entry.path);
                  setManualPath(entry.path);
                }}
                onDoubleClick={() => {
                  doBrowse(entry.path);
                }}
                className={`flex w-full items-center gap-2.5 border-b border-cursor-hairline-soft px-4 py-2.5 text-left text-sm transition-colors ${
                  isSelected
                    ? 'bg-cursor-primary/10 font-medium text-cursor-primary'
                    : 'text-cursor-ink hover:bg-cursor-surface-card'
                }`}
              >
                {isDcm ? (
                  <Layers className="h-4.5 w-4.5 flex-none text-cursor-primary" />
                ) : (
                  <Folder className="h-4.5 w-4.5 flex-none text-cursor-primary/80" />
                )}
                <span className="min-w-0 flex-1 truncate font-normal">{entry.name}</span>
                {isDcm && (
                  <span className="inline-flex flex-none items-center rounded bg-cursor-primary/10 px-1.5 py-0.5 text-xs font-medium text-cursor-primary">
                    {entry.slice_count ? `${entry.slice_count} slices` : 'DICOM'}
                  </span>
                )}
                {entry.size != null && (
                  <span className="flex-none text-right text-sm text-cursor-muted" style={{minWidth: '4.5rem'}}>
                    {fmtBytes(entry.size)}
                  </span>
                )}
              </button>
            );
          })}

        {/* Files (hidden when foldersOnly is true) */}
        {!isLoading &&
          !foldersOnly &&
          files.map((entry) => {
            const isImg = entry.selectable;
            const isSelected = selectedEntryPath === entry.path;
            return (
              <div
                key={entry.path}
                onClick={() => {
                  setSelectedEntryPath(entry.path);
                  setManualPath(entry.path);
                }}
                onDoubleClick={() => {
                  onConfirm(entry.path);
                }}
                className={`flex w-full cursor-pointer items-center gap-2.5 border-b border-cursor-hairline-soft px-4 py-2.5 text-sm transition-colors ${
                  isSelected
                    ? 'bg-cursor-primary/10 font-medium text-cursor-primary'
                    : 'text-cursor-ink hover:bg-cursor-surface-card'
                }`}
              >
                <FileText className="h-4.5 w-4.5 flex-none text-cursor-muted" />
                <span
                  title={entry.path}
                  className={`min-w-0 flex-1 truncate font-normal ${isImg ? 'text-cursor-ink' : 'text-cursor-muted'}`}
                >
                  {entry.name}
                </span>
                {entry.size != null && (
                  <span className="flex-none text-right text-sm text-cursor-muted" style={{minWidth: '4.5rem'}}>
                    {fmtBytes(entry.size)}
                  </span>
                )}
              </div>
            );
          })}
      </div>

      {/* Sticky footer */}
      <div className="flex items-center justify-between gap-2.5 border-t border-cursor-hairline bg-cursor-surface-card px-4 py-3">
        <div className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-sm text-cursor-muted">
          {selectedItemName ? (
            <>
              <span className="text-cursor-muted text-sm">Selected:</span>
              <span className="truncate text-sm font-medium text-cursor-ink" title={targetPathToConfirm}>
                {selectedItemName}
              </span>
            </>
          ) : null}
        </div>
        <div className="flex flex-none gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => onConfirm(targetPathToConfirm)}>
            {confirmBtnLabel}
          </Button>
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
  isConnected: boolean;
  remotePayload: Record<string, unknown> | RemotePayload;
  cacheKey: string;
  batchScanCache: BatchScanCache | null;
  setBatchScanCache: React.Dispatch<React.SetStateAction<BatchScanCache | null>>;
  initialSelectedPaths?: string[] | undefined;
}) {
  const remoteBrowseMutation = useRemoteBrowseMutation();
  const localBrowseMutation = useLocalBrowseMutation();
  const [count, setCount] = React.useState<number>(currentCount ?? 1);

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
  readOnly = true,
}: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  onChange?: (v: string) => void;
  onBrowse: () => void;
  browseLabel?: string;
  secondaryBrowse?: {
    label: string;
    onClick: () => void;
    title?: string;
  };
  required?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
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
          readOnly={readOnly}
          onChange={(e) => onChange?.(e.target.value)}
          className={`${inputCls} flex-1 ${disabled ? 'cursor-not-allowed bg-cursor-canvas-soft text-cursor-muted border-cursor-hairline-soft' : ''} ${readOnly ? 'bg-cursor-canvas-soft text-cursor-muted' : ''}`}
        />
        <Button
          variant="ghost"
          icon={<FolderOpen className="h-3.5 w-3.5" />}
          onClick={onBrowse}
          title={disabled ? 'Connect to server first' : browseLabel}
          disabled={disabled}
        >
          {browseLabel}
        </Button>
        {secondaryBrowse && (
          <Button
            variant="ghost"
            icon={<FolderOpen className="h-3.5 w-3.5" />}
            onClick={secondaryBrowse.onClick}
            title={disabled ? 'Connect to server first' : (secondaryBrowse.title ?? secondaryBrowse.label)}
            disabled={disabled}
          >
            {secondaryBrowse.label}
          </Button>
        )}
      </div>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Radio group helper
// ---------------------------------------------------------------------------

function RadioCard({
  name,
  label,
  value,
  selectedValue,
  hint,
  disabled = false,
  onChange,
}: {
  name: string;
  label: string;
  value: string;
  selectedValue: string;
  hint?: string | undefined;
  disabled?: boolean | undefined;
  onChange: (v: string) => void;
}) {
  const isSelected = selectedValue === value;
  return (
    <label
      className={`flex h-full min-h-[3.75rem] items-start gap-2.5 rounded-lg border px-3 py-2 transition-colors select-none ${
        disabled
          ? 'border-cursor-hairline-soft bg-cursor-canvas-soft/50 text-cursor-muted opacity-50 cursor-not-allowed'
          : isSelected
            ? 'border-cursor-primary/30 bg-cursor-primary/10 text-cursor-primary cursor-pointer'
            : 'border-cursor-hairline-soft bg-cursor-surface-card text-cursor-ink hover:border-cursor-hairline hover:bg-cursor-canvas-soft cursor-pointer'
      }`}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={isSelected}
        disabled={disabled}
        onChange={() => !disabled && onChange(value)}
        className="mt-0.5 h-3.5 w-3.5 flex-none accent-cursor-primary cursor-pointer"
      />
      <span className="grid gap-0.5 min-w-0">
        <span className={`text-sm font-semibold leading-tight ${isSelected ? 'text-cursor-primary' : 'text-cursor-ink'}`}>
          {label}
        </span>
        {hint && (
          <span className={`text-xs font-normal leading-relaxed ${isSelected ? 'text-cursor-primary/80' : 'text-cursor-muted'}`}>
            {hint}
          </span>
        )}
      </span>
    </label>
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
  const remotePayload = buildRemotePayload(formValues);

  // Derived helpers
  const isLocal = formValues.runtimeTarget === 'Local';
  const isBatch = formValues.pipelineMode === 'Batch' || formValues.inputMode === 'batch_folder';
  const inputSource = formValues.inputSource || 'Local';

  // Local modals
  const [dualPaneModal, setDualPaneModal] = React.useState(false);
  const [serverInputModal, setServerInputModal] = React.useState(false);
  const [serverInputFoldersOnly, setServerInputFoldersOnly] = React.useState(false);
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
    try {
      const selected = await open({
        multiple: false,
        filters: [{name: 'MRI Images', extensions: ['nii', 'nii.gz', 'dcm', 'ima']}],
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
    try {
      const selected = await open({directory: true, multiple: false});
      const path = selectedDialogPath(selected);
      if (path) {
        setFormField('inputPath', path);
        if (isBatch) setBatchModal(true);
      }
    } catch {
      // dialog cancelled or unavailable
    }
  };

  const handleLocalBrowseOutputDir = async () => {
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

  return (
    <>
      <Panel icon={<FolderInput className="h-4 w-4 text-cursor-primary" />} title="Input & Output" className="min-w-0">
        <div className="grid gap-4">
          {/* Row 1: Source + Input Mode — Synchronized CSS Grid */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 items-stretch">
            {/* Headers */}
            <span className="text-sm font-medium leading-[1.3] text-cursor-body">Source Input</span>
            <span className="text-sm font-medium leading-[1.3] text-cursor-body">Input Mode</span>

            {/* Row 1 cards: Local & Single input */}
            <RadioCard
              name="inputSource"
              label={sourceOptions[0]?.label ?? ''}
              value={sourceOptions[0]?.value ?? ''}
              selectedValue={inputSource}
              hint={sourceOptions[0]?.hint}
              disabled={sourceOptions[0]?.disabled}
              onChange={(v) => setFormField('inputSource', v)}
            />
            <RadioCard
              name="inputMode"
              label={inputModeOptions[0]?.label ?? ''}
              value={inputModeOptions[0]?.value ?? ''}
              selectedValue={isBatch ? 'batch_folder' : 'file'}
              hint={inputModeOptions[0]?.hint}
              onChange={(v) => setFormField('inputMode', v)}
            />

            {/* Row 2 cards: Server & Batch input */}
            <RadioCard
              name="inputSource"
              label={sourceOptions[1]?.label ?? ''}
              value={sourceOptions[1]?.value ?? ''}
              selectedValue={inputSource}
              hint={sourceOptions[1]?.hint}
              disabled={sourceOptions[1]?.disabled}
              onChange={(v) => setFormField('inputSource', v)}
            />
            <RadioCard
              name="inputMode"
              label={inputModeOptions[1]?.label ?? ''}
              value={inputModeOptions[1]?.value ?? ''}
              selectedValue={isBatch ? 'batch_folder' : 'file'}
              hint={inputModeOptions[1]?.hint}
              onChange={(v) => setFormField('inputMode', v)}
            />

            {/* Row 3: Actions row (Aligned) */}
            <div className="min-h-8 flex items-center gap-2">
              {!isLocal && (
                <Button
                  type="button"
                  variant="ghost"
                  icon={<Upload className="h-3.5 w-3.5" />}
                  onClick={() => setDualPaneModal(true)}
                  disabled={!remoteConnected}
                >
                  Upload data to server
                </Button>
              )}
            </div>
            <div className="min-h-8 flex items-center gap-2">
              {isBatch && formValues.batchImageCount !== undefined && (
                <span className="text-xs text-cursor-muted">{formValues.batchImageCount} selected</span>
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
                  label="Input location (local path)"
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
                  label="Input location (local path)"
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
                label="Input location (server path)"
                value={formValues.inputServerDir || ''}
                placeholder="~/mri-uploads"
                onChange={(v) => setFormField('inputServerDir', v)}
                onBrowse={() => setServerStagingModal(true)}
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
              {isBatch ? (
                <PathField
                  id="inputServerDir"
                  label="Input location (server path)"
                  value={formValues.inputServerDir || ''}
                  placeholder="/home/user/batch_subjects_folder"
                  onChange={(v) => setFormField('inputServerDir', v)}
                  onBrowse={() => {
                    setServerInputFoldersOnly(true);
                    setServerInputModal(true);
                  }}
                  browseLabel="Browse Folder"
                  disabled={!remoteConnected}
                  required
                />
              ) : (
                <PathField
                  id="inputServerDir"
                  label="Input location (server path)"
                  value={formValues.inputServerDir || ''}
                  placeholder="/home/user/sub-001_T1w.nii.gz or /home/user/dicom_series_folder"
                  onChange={(v) => setFormField('inputServerDir', v)}
                  onBrowse={() => {
                    setServerInputFoldersOnly(false);
                    setServerInputModal(true);
                  }}
                  browseLabel="Browse File"
                  secondaryBrowse={{
                    label: 'Folder (DICOM)',
                    title: 'Browse DICOM series folder',
                    onClick: () => {
                      setServerInputFoldersOnly(true);
                      setServerInputModal(true);
                    },
                  }}
                  disabled={!remoteConnected}
                  required
                />
              )}
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
            title="Input location (server path)"
            initialPath={formValues.inputServerDir || '~'}
            remotePayload={remotePayload}
            foldersOnly={true}
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
            title="Input location (server path)"
            initialPath={formValues.inputServerDir || '~'}
            remotePayload={remotePayload}
            foldersOnly={serverInputFoldersOnly}
            onConfirm={(p) => {
              setFormField('inputServerDir', p);
              setServerInputModal(false);
              if (isBatch) setBatchModal(true);
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
            title="Output location (server path)"
            initialPath={formValues.serverOutputDir || '~'}
            remotePayload={remotePayload}
            foldersOnly={true}
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
          inputPath={inputSource === 'Server' ? (formValues.inputServerDir || '') : formValues.inputPath}
          currentCount={formValues.batchImageCount as number | undefined}
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

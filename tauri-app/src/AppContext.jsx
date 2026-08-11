import React, {useCallback, useEffect, useRef, useState} from 'react';
import {BackendClient, buildRunConfig} from './api.js';
import {normalizeJob} from './jobFormatters.js';

const AppContext = React.createContext(null);

const DEFAULT_FORM_VALUES = {
  pipelineMode: 'Custom',
  inputSource: 'Local',
  inputMode: 'file',
  inputPath: '',
  additionalInputPaths: '',
  outputDir: '',
  runtimeTarget: 'Local',
  ramPercent: 80,
  cpuThreads: 4,
  gpuMode: 'auto',
  host: '',
  port: 22,
  username: '',
  remote_python: 'python3',
  workspace: '~/mri-remote-jobs',
  key_path: '',
  password: '',
};

export function AppProvider({children}) {
  const clientRef = useRef(new BackendClient());

  const [activeTab, setActiveTab] = useState('pipeline');
  const [metadata, setMetadata] = useState(null);
  const [environment, setEnvironment] = useState(null);
  const [formValues, setFormValues] = useState({...DEFAULT_FORM_VALUES});
  const [selectedStatsAtlases, setSelectedStatsAtlases] = useState({});
  const [remoteResult, setRemoteResult] = useState({
    ok: false,
    connected: false,
    config: null,
    hardware: null,
    error: '',
    jobs: [],
    warnings: [],
  });
  const [latestImages, setLatestImages] = useState([]);
  const [imageSelection, setImageSelection] = useState(new Set());
  const [imageSearch, setImageSearch] = useState('');
  const [imageLogText, setImageLogText] = useState('Docker image log is idle.');
  const [latestJobs, setLatestJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [jobEvents, setJobEvents] = useState([]);
  const [jobLogSearch, setJobLogSearch] = useState('');
  const [outputText, setOutputText] = useState('Log stream is idle.');
  const [preparedRequest, setPreparedRequest] = useState(null);
  const [busy, setBusy] = useState({
    connect: false,
    listRemote: false,
    refreshTools: false,
    refreshJobs: false,
    checkEnv: false,
  });
  const [toolMessage, setToolMessage] = useState('Image status is not loaded.');

  const setBusyKey = useCallback((key, value) => {
    setBusy((prev) => ({...prev, [key]: value}));
  }, []);

  const print = useCallback((label, payload) => {
    const block = `${label}\n${JSON.stringify(payload, null, 2)}\n\n`;
    setOutputText((prev) => `${block}${prev}`);
  }, []);

  const appendImageLog = useCallback((line) => {
    const timestamp = new Date().toLocaleTimeString();
    setImageLogText((prev) => `[${timestamp}] ${line}\n${prev}`.trim());
  }, []);

  const selectedRuntimeTarget = useCallback(() => (formValues.runtimeTarget === 'Server' ? 'Server' : 'Local'), [formValues.runtimeTarget]);

  const remotePayload = useCallback(
    () => ({
      host: formValues.host,
      port: formValues.port,
      username: formValues.username,
      password: formValues.password,
      remote_python: formValues.remote_python,
      workspace: formValues.workspace,
      key_path: formValues.key_path,
    }),
    [formValues],
  );

  const initializeStatsAtlasSelection = useCallback((meta) => {
    const selection = {};
    for (const [statKey, stat] of Object.entries(meta?.stats_vectors || {})) {
      const atlases = Array.isArray(stat.atlases) ? stat.atlases : [];
      selection[statKey] = statKey === 'cortical_thickness' ? atlases.slice(0, 2) : atlases.slice(0, 1);
    }
    setSelectedStatsAtlases(selection);
    return selection;
  }, []);

  const startup = useCallback(async () => {
    const client = clientRef.current;
    await client.waitForHealth();
    const env = await client.localEnvironment();
    setEnvironment(env);
    const meta = await client.metadata();
    setMetadata(meta);
    initializeStatsAtlasSelection(meta);
    print('Metadata loaded', {modes: meta.pipeline_modes.length, stages: meta.stages.length});
  }, [initializeStatsAtlasSelection, print]);

  const refreshEnvironment = useCallback(async () => {
    const client = clientRef.current;
    setBusyKey('checkEnv', true);
    try {
      const env = await client.localEnvironment();
      setEnvironment(env);
      print('Environment status', env);
    } catch (error) {
      print('Refresh environment failed', {error: error.message});
    } finally {
      setBusyKey('checkEnv', false);
    }
  }, [print, setBusyKey]);

  const setFormField = useCallback((name, value) => {
    setFormValues((prev) => ({...prev, [name]: value}));
  }, []);

  const setFormFields = useCallback((patch) => {
    setFormValues((prev) => ({...prev, ...patch}));
  }, []);

  const refreshTools = useCallback(async () => {
    const client = clientRef.current;
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
      const result = await client.localImageStatus(selectedTools, {
        target,
        remote: target === 'Server' ? remotePayload() : null,
      });
      if (!result.ok) {
        setToolMessage(result.error || `${target} Docker image check failed.`);
        setLatestImages([]);
        setImageSelection(new Set());
        appendImageLog(`${target} Image status failed: ${result.error || 'unknown error'}`);
        return;
      }
      const images = Array.isArray(result.images) ? result.images : [];
      setLatestImages(images);
      setImageSelection(new Set());
      appendImageLog(`Refreshed ${images.length} ${target} Docker image records.`);
    } catch (error) {
      setToolMessage(`${target} Docker check failed: ${error.message || 'unknown error'}`);
      setLatestImages([]);
      setImageSelection(new Set());
      appendImageLog(`${target} Docker check failed: ${error.message || 'unknown error'}`);
    } finally {
      setBusyKey('refreshTools', false);
    }
  }, [selectedRuntimeTarget, remoteResult.connected, metadata, formValues.pipelineMode, remotePayload, appendImageLog, setBusyKey]);

  const loadJobDetails = useCallback(async (jobId) => {
    if (!jobId) {
      setJobEvents([]);
      setOutputText('Log stream is idle.');
      return;
    }
    const client = clientRef.current;
    const [eventsResult, logResult] = await Promise.all([
      client.readLocalEvents(jobId).catch(() => ({events: []})),
      client.readLocalLog(jobId, 0, 65536).catch(() => ({text: ''})),
    ]);
    const events = Array.isArray(eventsResult.events) ? eventsResult.events : [];
    setJobEvents(events);
    setOutputText(logResult.text || '');
  }, []);

  const refreshJobs = useCallback(async () => {
    const client = clientRef.current;
    setBusyKey('refreshJobs', true);
    try {
      const localRes = await client.listLocalJobs().catch(() => ({jobs: []}));
      const remoteRes = remoteResult.connected ? await client.listRemoteJobs(remotePayload()).catch(() => ({jobs: []})) : {jobs: []};
      const localJobs = (Array.isArray(localRes.jobs) ? localRes.jobs : []).map((j) => normalizeJob(j, 'Local'));
      const remoteJobs = (Array.isArray(remoteRes.jobs) ? remoteRes.jobs : []).map((j) => normalizeJob(j, 'Server'));
      const jobs = [...localJobs, ...remoteJobs];
      setLatestJobs(jobs);

      let nextSelected = selectedJobId;
      if (jobs.length && (!nextSelected || !jobs.some((j) => j.job_id === nextSelected))) {
        nextSelected = jobs[0].job_id;
        setSelectedJobId(nextSelected);
      }
      const currentJob = jobs.find((j) => j.job_id === nextSelected);
      await loadJobDetails(currentJob ? nextSelected : '');
    } catch (err) {
      print('Refresh jobs failed', {error: err.message});
    } finally {
      setBusyKey('refreshJobs', false);
    }
  }, [remoteResult.connected, remotePayload, selectedJobId, loadJobDetails, print, setBusyKey]);

  const switchTab = useCallback((tab) => {
    setActiveTab(tab);
  }, []);

  const selectJob = useCallback(async (jobId) => {
    setSelectedJobId(jobId);
    setActiveTab('jobs');
    await loadJobDetails(jobId);
  }, [loadJobDetails]);

  const connectRemote = useCallback(async () => {
    const client = clientRef.current;
    setRemoteResult((prev) => ({...prev, ok: false, connected: false, error: '', jobs: [], hardware: null}));
    setBusyKey('connect', true);
    setBusyKey('listRemote', true);
    try {
      const result = await client.validateRemoteConfig(remotePayload());
      renderRemoteResult(result);
      if (result.ok && result.connected === true && selectedRuntimeTarget() === 'Server') {
        await refreshTools();
      }
    } catch (error) {
      renderRemoteResult({ok: false, connected: false, error: error.message || 'SSH connection failed.'});
      print('Remote connect failed', {error: error.message});
    } finally {
      setBusyKey('connect', false);
      setBusyKey('listRemote', false);
    }
  }, [remotePayload, selectedRuntimeTarget, refreshTools, print, setBusyKey]);

  const listRemoteJobs = useCallback(async () => {
    const client = clientRef.current;
    setBusyKey('listRemote', true);
    try {
      const result = await client.listRemoteJobs(remotePayload());
      renderRemoteResult(result);
      print('Remote jobs', result);
    } catch (error) {
      renderRemoteResult({ok: false, connected: false, error: error.message || 'Remote job listing failed.'});
      print('Remote jobs failed', {error: error.message});
    } finally {
      setBusyKey('listRemote', false);
    }
  }, [remotePayload, print, setBusyKey]);

  function renderRemoteResult(result) {
    if (!result.ok) {
      setRemoteResult({
        ok: false,
        connected: false,
        config: null,
        hardware: null,
        error: result.error || (result.errors || []).join(' ') || 'SSH connection failed.',
        jobs: [],
        warnings: [],
      });
      return;
    }
    if (Array.isArray(result.jobs)) {
      setRemoteResult({
        ok: true,
        connected: false,
        config: result.config || null,
        hardware: result.hardware || null,
        error: '',
        jobs: result.jobs,
        warnings: Array.isArray(result.warnings) ? result.warnings : [],
      });
      return;
    }
    if (result.connected !== true) {
      setRemoteResult({
        ok: true,
        connected: false,
        config: null,
        hardware: null,
        error: 'SSH connection was not confirmed. Restart NeuroFlow so the updated backend is used, then press Connect again.',
        jobs: [],
        warnings: [],
      });
      return;
    }
    setRemoteResult({
      ok: true,
      connected: true,
      config: result.config || {},
      hardware: result.hardware || {},
      error: '',
      jobs: [],
      warnings: Array.isArray(result.warnings) ? result.warnings : [],
    });
  }

  const prepareRunRequest = useCallback(async () => {
    const client = clientRef.current;
    const config = buildRunConfig(formValues, metadata);
    const request = await client.prepareRunRequest(config);
    setPreparedRequest(request);
    print('Prepared run request', request);
    return request;
  }, [formValues, metadata, print]);

  const startPipeline = useCallback(async () => {
    const client = clientRef.current;
    let request = preparedRequest;
    if (!request?.request) {
      request = await prepareRunRequest();
      if (!request?.ok) return;
    }
    if (!request?.request) return;
    const result = await client.startLocalJob(request.request);
    print('Started local job', result);
    await refreshJobs();
    setActiveTab('jobs');
  }, [preparedRequest, prepareRunRequest, refreshJobs, print]);

  const clearJobLog = useCallback(() => {
    setOutputText('');
  }, []);

  const handlePipelineModeChange = useCallback(
    (value) => {
      setFormValues((prev) => {
        const presetTools = metadata?.presets?.[value]?.tools || {};
        const next = {...prev, pipelineMode: value};
        for (const stage of metadata?.stages || []) {
          next[`stage_${stage.id}`] = presetTools[stage.id] || '';
        }
        return next;
      });
      refreshTools();
    },
    [metadata, refreshTools],
  );

  const handleRuntimeTargetChange = useCallback(
    (value) => {
      setFormValues((prev) => ({...prev, runtimeTarget: value}));
      refreshTools();
    },
    [refreshTools],
  );

  const applyWorkspaceConfig = useCallback(
    (workspace) => {
      const remote = workspace.remote || {};
      setFormValues((prev) => ({
        ...prev,
        inputSource: workspace.input_source || (workspace.run_target === 'Server' ? 'Server' : 'Local'),
        inputMode: workspace.input_mode || 'file',
        inputPath: workspace.input_path || '',
        additionalInputPaths: Array.isArray(workspace.selected_files) ? workspace.selected_files.join(', ') : '',
        outputDir: workspace.output_dir || '',
        runtimeTarget: workspace.run_target === 'Server' ? 'Server' : 'Local',
        ramPercent: workspace.ram_percent ?? 100,
        cpuThreads: workspace.threads ?? 4,
        gpuMode: workspace.device === 'cuda' || workspace.device === 'gpu' ? 'enabled' : 'disabled',
        host: remote.host || '',
        port: remote.port ?? 22,
        username: remote.username || '',
        remote_python: remote.python || 'python3',
        workspace: remote.workspace || '~/mri-remote-jobs',
        key_path: remote.key_path || '',
      }));
      setPreparedRequest(null);
    },
    [],
  );

  const applyPresetConfig = useCallback(
    (preset) => {
      if (preset.pipeline_mode) {
        setFormValues((prev) => ({...prev, pipelineMode: preset.pipeline_mode}));
      }
      const tools = preset.tools || {};
      setFormValues((prev) => {
        const next = {...prev};
        for (const [stage, toolKey] of Object.entries(tools)) {
          next[`stage_${stage}`] = String(toolKey);
        }
        return next;
      });
      setSelectedStatsAtlases((prev) => {
        const statsVectors = preset.stats_vectors || {};
        const next = {...prev};
        for (const statKey of Object.keys(next)) {
          const stat = statsVectors[statKey];
          if (stat && Array.isArray(stat.atlases)) next[statKey] = stat.atlases;
          else if (Array.isArray(stat)) next[statKey] = stat;
        }
        return next;
      });
      setPreparedRequest(null);
    },
    [],
  );

  const removeAtlas = useCallback(
    (statKey, atlasKey) => {
      const atlas = metadata?.atlases?.[atlasKey] || {label: atlasKey};
      if (!window.confirm(`Remove atlas "${atlas.label || atlasKey}" from this stats vector?`)) {
        return;
      }
      setSelectedStatsAtlases((prev) => ({
        ...prev,
        [statKey]: (prev[statKey] || []).filter((key) => key !== atlasKey),
      }));
    },
    [metadata],
  );

  const addAtlas = useCallback((statKey, atlasKey) => {
    setSelectedStatsAtlases((prev) => ({
      ...prev,
      [statKey]: [...(prev[statKey] || []), atlasKey],
    }));
  }, []);

  useEffect(() => {
    startup().catch((error) => print('Startup failed', {error: error.message}));
  }, [startup, print]);

  const value = {
    activeTab,
    switchTab,
    metadata,
    environment,
    formValues,
    setFormField,
    setFormFields,
    handlePipelineModeChange,
    handleRuntimeTargetChange,
    selectedRuntimeTarget,
    selectedStatsAtlases,
    addAtlas,
    removeAtlas,
    remoteResult,
    connectRemote,
    listRemoteJobs,
    latestImages,
    latestJobs,
    imageSelection,
    setImageSelection,
    imageSearch,
    setImageSearch,
    imageLogText,
    appendImageLog,
    selectedJobId,
    jobLogSearch,
    setJobLogSearch,
    jobEvents,
    outputText,
    clearJobLog,
    refreshJobs,
    refreshTools,
    refreshEnvironment,
    selectJob,
    startPipeline,
    preparedRequest,
    setPreparedRequest,
    toolMessage,
    setToolMessage,
    busy,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const context = React.useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within AppProvider.');
  }
  return context;
}

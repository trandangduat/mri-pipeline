import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeAll, expect, test, vi} from 'vitest';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router';
import {AppHeader} from '../src/components/AppHeader';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

function renderHeader(props: {
  activeTab?: 'pipeline' | 'tools' | 'jobs';
  onSelectTab?: (tab: 'pipeline' | 'tools' | 'jobs') => void;
  jobsCount?: number;
} = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {queries: {retry: false}},
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AppHeader
          activeTab={props.activeTab || 'pipeline'}
          onSelectTab={props.onSelectTab || vi.fn()}
          jobsCount={props.jobsCount ?? 5}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('renders all 3 horizontal tabs with jobs count badge', () => {
  renderHeader({jobsCount: 42});

  expect(screen.getByText('Pipeline Configuration')).toBeInTheDocument();
  expect(screen.getByText('Tools Configuration')).toBeInTheDocument();
  expect(screen.getByText('Jobs Monitor')).toBeInTheDocument();
  expect(screen.getByText('42')).toBeInTheDocument();
});

test('triggers onSelectTab callback when clicking tabs', async () => {
  const user = userEvent.setup();
  const onSelectTab = vi.fn();

  renderHeader({activeTab: 'pipeline', onSelectTab});

  await user.click(screen.getByText('Tools Configuration'));
  expect(onSelectTab).toHaveBeenCalledWith('tools');

  await user.click(screen.getByText('Jobs Monitor'));
  expect(onSelectTab).toHaveBeenCalledWith('jobs');
});

test('renders workspace and pipeline action buttons', () => {
  renderHeader();

  expect(screen.getByText('Save Workspace')).toBeInTheDocument();
  expect(screen.getByText('Load Workspace')).toBeInTheDocument();
  expect(screen.getByText('Start Pipeline')).toBeInTheDocument();
  expect(screen.queryByText('Stop Pipeline')).not.toBeInTheDocument();
});

test('save workspace persists all NeuroFLOW settings', async () => {
  const originalFetch = globalThis.fetch;
  const originalPrompt = globalThis.prompt;
  const saveCalls: Array<{url: string; body: Record<string, unknown>}> = [];
  const metadataPayload = {
    version: 1,
    project_root: '/p',
    pipeline_modes: [],
    presets: {},
    stages: [],
    stage_order: [],
    fs7_recon_style_stage_order: [],
    tools: {},
    tools_by_stage: {},
    export_items: {},
    export_defaults: {},
    stats_vectors: {},
    atlases: {},
    vector_specs: {},
  };
  globalThis.fetch = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    const u = String(url);
    if (options?.body) {
      saveCalls.push({url: u, body: JSON.parse(String(options.body)) as Record<string, unknown>});
    }
    if (u.includes('/metadata')) {
      return {ok: true, json: async () => metadataPayload} as Response;
    }
    if (u.includes('/config/workspaces/save')) {
      return {ok: true, json: async () => ({ok: true})} as Response;
    }
    return {ok: true, json: async () => ({})} as Response;
  });
  vi.stubGlobal('prompt', vi.fn(() => 'NeuroFLOW workspace'));
  const user = userEvent.setup();

  usePipelineFormStore.setState({
    formValues: {
      ...usePipelineFormStore.getState().formValues,
      pipelineMode: 'FreeSurfer 8 + Volume',
      neuroflowEnabled: true,
      neuroflowMaxConcurrentTasks: 1,
      neuroflowMaxRetries: 2,
      neuroflowWarmupEnabled: true,
      neuroflowWarmupInitialConcurrency: 1,
      neuroflowWarmupSafeSuccesses: 5,
      neuroflowPreserveOomBounds: false,
      neuroflowEstimationMode: 'conservative',
      neuroflowMaxIoHeavyTasks: 3,
      neuroflowMachineProfileId: 'workstation_32c',
    },
  });

  try {
    renderHeader();
    await user.click(screen.getByText('Save Workspace'));

    const save = saveCalls.find((call) => call.url.includes('/config/workspaces/save'));
    expect(save).toBeDefined();
    const data = (save?.body?.data || {}) as Record<string, unknown>;
    expect(data.neuroflow_enabled).toBe(true);
    expect(data.neuroflow_max_concurrent_tasks).toBe(1);
    expect(data.neuroflow_max_retries).toBe(2);
    expect(data.neuroflow_warmup_enabled).toBe(true);
    expect(data.neuroflow_warmup_initial_concurrency).toBe(1);
    expect(data.neuroflow_warmup_safe_successes).toBe(5);
    expect(data.neuroflow_preserve_oom_bounds).toBe(false);
    expect(data.neuroflow_estimation_mode).toBe('conservative');
    expect(data.neuroflow_max_io_heavy_tasks).toBe(3);
    expect(data.neuroflow_machine_profile_id).toBe('application_default');
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.prompt = originalPrompt;
    vi.unstubAllGlobals();
  }
});

test('shows warning modal when an active job is running on the target machine', async () => {
  const {useJobsStore} = await import('../src/stores/jobsStore');
  useJobsStore.getState().setLatestJobs([
    {
      job_id: 'job_active_1',
      target: 'Local',
      state: 'running',
    },
  ]);

  const user = userEvent.setup();
  renderHeader();

  await user.click(screen.getByText('Start Pipeline'));

  expect(screen.getByText('Job Already Running')).toBeInTheDocument();
  expect(screen.getByText(/job_active_1/)).toBeInTheDocument();
  expect(screen.getByText('Run Anyway')).toBeInTheDocument();
  expect(screen.getByText('Cancel')).toBeInTheDocument();

  // Clicking Cancel dismisses modal
  await user.click(screen.getByText('Cancel'));
  expect(screen.queryByText('Job Already Running')).not.toBeInTheDocument();
});

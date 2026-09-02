import {act, fireEvent, render, screen} from '@testing-library/react';
import {beforeAll, expect, test, vi} from 'vitest';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {AdvancedSettingsSection} from '../src/pages/PipelinePage';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';

const {mockOpen, mockValidateNeuroflowConfig} = vi.hoisted(() => ({
  mockOpen: vi.fn(),
  mockValidateNeuroflowConfig: vi.fn(),
}));

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: mockOpen,
}));

vi.mock('../src/query/useEnvironment', () => ({
  useMetadata: () => ({
    data: {
      version: 1,
      stages: [],
      stage_order: [],
      tools: {},
      tools_by_stage: {},
      pipeline_modes: [{id: 'CAT12 + Volume'}, {id: 'FreeSurfer 8 + Volume'}, {id: 'Custom'}],
      presets: {},
      stats_vectors: {},
      atlases: {},
      tool_contracts: {},
    },
    isLoading: false,
    isError: false,
  }),
  useEnvironment: () => ({
    data: {docker_available: true, local_hardware: {}},
    isLoading: false,
    isError: false,
  }),
  useClient: () => ({
    validateNeuroflowConfig: mockValidateNeuroflowConfig,
  }),
}));

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

beforeEach(() => {
  vi.clearAllMocks();
});

function resetStore() {
  usePipelineFormStore.getState().resetForm();
}

function renderSection() {
  const queryClient = new QueryClient({
    defaultOptions: {queries: {retry: false}},
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdvancedSettingsSection />
    </QueryClientProvider>,
  );
}

test('requires both configuration files before enabling NeuroFLOW in Custom mode', () => {
  resetStore();
  usePipelineFormStore.getState().setFormFields({
    pipelineMode: 'Custom',
    neuroflowPresetFile: '',
    neuroflowProfileFile: '',
  });

  renderSection();

  expect(
    screen.getByText('Select both a NeuroFLOW preset and profile configuration to enable the scheduler for a custom pipeline.'),
  ).toBeInTheDocument();
  const toggle = screen.getByRole('checkbox', {name: /Use NeuroFLOW scheduler/i});
  expect(toggle).toBeDisabled();
  expect(toggle).not.toBeChecked();
  expect(screen.queryByText('Max parallel tasks')).not.toBeInTheDocument();
});

test('allows NeuroFLOW with custom preset and profile files', () => {
  resetStore();
  usePipelineFormStore.getState().setFormFields({
    pipelineMode: 'Custom',
    neuroflowPresetFile: '/tmp/custom-preset.yaml',
    neuroflowProfileFile: '/tmp/custom-profile.yaml',
  });

  renderSection();

  const toggle = screen.getByRole('checkbox', {name: /Use NeuroFLOW scheduler/i});
  expect(toggle).toBeEnabled();
  expect(toggle).toBeChecked();
});

test('uses the expected NeuroFLOW scheduler defaults', () => {
  resetStore();
  const {formValues} = usePipelineFormStore.getState();

  expect(formValues.neuroflowEnabled).toBe(true);
  expect(formValues.neuroflowMaxConcurrentTasks).toBe(2);
  expect(formValues.neuroflowPolicy).toBe('B6');
  expect(formValues.neuroflowMaxRetries).toBe(3);
  expect(formValues.neuroflowWarmupEnabled).toBe(true);
  expect(formValues.neuroflowWarmupInitialConcurrency).toBe(2);
  expect(formValues.neuroflowWarmupSafeSuccesses).toBe(3);
  expect(formValues.neuroflowPreserveOomBounds).toBe(true);
  expect(formValues.neuroflowEstimationMode).toBe('balanced');
  expect(formValues.neuroflowMaxIoHeavyTasks).toBe(2);
  expect(formValues.neuroflowMachineProfileId).toBe('application_default');
});

test('shows NeuroFLOW fields for preset mode', () => {
  resetStore();
  usePipelineFormStore.getState().setFormField('pipelineMode', 'FreeSurfer 8 + Volume');
  usePipelineFormStore.getState().setFormField('neuroflowEnabled', true);
  usePipelineFormStore.getState().setFormField('neuroflowMaxConcurrentTasks', 2);

  renderSection();

  const toggle = screen.getByRole('checkbox', {name: /Use NeuroFLOW scheduler/i});
  expect(toggle).toBeEnabled();
  expect(toggle).toBeChecked();
  expect(screen.getByRole('button', {name: /Show Settings/i})).toBeInTheDocument();
  expect(screen.queryByText('Max parallel tasks')).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', {name: /Show Settings/i}));

  expect(screen.getByText('Max parallel tasks')).toBeInTheDocument();
  expect(screen.getByText('Queue Policy')).toBeInTheDocument();
  expect(screen.getByText(/Preset configuration/)).toBeInTheDocument();
  expect(screen.getByText(/Profile configuration/)).toBeInTheDocument();
  expect(screen.getByText('Start safely, then scale up')).toBeInTheDocument();
});

test('hides settings toggle when NeuroFLOW scheduler is disabled', () => {
  resetStore();
  usePipelineFormStore.getState().setFormField('pipelineMode', 'FreeSurfer 8 + Volume');
  usePipelineFormStore.getState().setFormField('neuroflowEnabled', false);

  renderSection();

  const toggle = screen.getByRole('checkbox', {name: /Use NeuroFLOW scheduler/i});
  expect(toggle).not.toBeChecked();
  expect(screen.queryByRole('button', {name: /Show Settings/i})).not.toBeInTheDocument();
  expect(screen.queryByText('Max parallel tasks')).not.toBeInTheDocument();
});

test('opens and dismisses invalid preset popup modal when an invalid file is selected', async () => {
  resetStore();
  usePipelineFormStore.getState().setFormFields({
    pipelineMode: 'Custom',
    neuroflowPresetFile: '/tmp/preset.yaml',
    neuroflowProfileFile: '/tmp/profile.yaml',
  });

  mockOpen.mockResolvedValue('/tmp/invalid.yaml');
  mockValidateNeuroflowConfig.mockResolvedValue({ok: false, error: 'Invalid preset'});

  renderSection();
  fireEvent.click(screen.getByRole('button', {name: /Show Settings/i}));

  await act(async () => {
    fireEvent.click(screen.getByRole('button', {name: 'Browse preset configuration'}));
  });

  // Modal appears
  expect(await screen.findByText('Invalid preset file')).toBeInTheDocument();
  expect(screen.getByText('The selected file is not a valid NeuroFLOW preset configuration.')).toBeInTheDocument();

  // Click OK to dismiss
  fireEvent.click(screen.getByRole('button', {name: 'OK'}));
  expect(screen.queryByText('Invalid preset file')).not.toBeInTheDocument();
});

test('opens and dismisses invalid profile popup modal when an invalid file is selected', async () => {
  resetStore();
  usePipelineFormStore.getState().setFormFields({
    pipelineMode: 'Custom',
    neuroflowPresetFile: '/tmp/preset.yaml',
    neuroflowProfileFile: '/tmp/profile.yaml',
  });

  mockOpen.mockResolvedValue('/tmp/invalid_profile.yaml');
  mockValidateNeuroflowConfig.mockResolvedValue({ok: false, error: 'Invalid profile'});

  renderSection();
  fireEvent.click(screen.getByRole('button', {name: /Show Settings/i}));

  await act(async () => {
    fireEvent.click(screen.getByRole('button', {name: 'Browse profile configuration'}));
  });

  // Modal appears
  expect(await screen.findByText('Invalid profile file')).toBeInTheDocument();
  expect(screen.getByText('The selected file is not a valid NeuroFLOW profile configuration.')).toBeInTheDocument();

  // Click OK to dismiss
  fireEvent.click(screen.getByRole('button', {name: 'OK'}));
  expect(screen.queryByText('Invalid profile file')).not.toBeInTheDocument();
});

test('preset and profile inputs are read-only', () => {
  resetStore();
  usePipelineFormStore.getState().setFormFields({
    pipelineMode: 'Custom',
    neuroflowPresetFile: '/tmp/preset.yaml',
    neuroflowProfileFile: '/tmp/profile.yaml',
  });

  renderSection();
  fireEvent.click(screen.getByRole('button', {name: /Show Settings/i}));

  const presetInput = screen.getByPlaceholderText('Select preset YAML/JSON via Browse');
  const profileInput = screen.getByPlaceholderText('Select profile YAML/JSON via Browse');

  expect(presetInput).toHaveAttribute('readonly');
  expect(profileInput).toHaveAttribute('readonly');
});


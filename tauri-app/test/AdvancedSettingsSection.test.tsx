import {fireEvent, render, screen} from '@testing-library/react';
import {beforeAll, expect, test, vi} from 'vitest';
import {AdvancedSettingsSection} from '../src/pages/PipelinePage';
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

function resetStore() {
  usePipelineFormStore.getState().resetForm();
}

test('requires both configuration files before enabling NeuroFLOW in Custom mode', () => {
  resetStore();
  usePipelineFormStore.getState().setFormFields({
    pipelineMode: 'Custom',
    neuroflowPresetFile: '',
    neuroflowProfileFile: '',
  });

  render(<AdvancedSettingsSection />);

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

  render(<AdvancedSettingsSection />);

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

  render(<AdvancedSettingsSection />);

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

  render(<AdvancedSettingsSection />);

  const toggle = screen.getByRole('checkbox', {name: /Use NeuroFLOW scheduler/i});
  expect(toggle).not.toBeChecked();
  expect(screen.queryByRole('button', {name: /Show Settings/i})).not.toBeInTheDocument();
  expect(screen.queryByText('Max parallel tasks')).not.toBeInTheDocument();
});

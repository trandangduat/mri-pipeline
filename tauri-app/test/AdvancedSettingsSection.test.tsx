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

test('shows unsupported-mode notice and disables NeuroFLOW toggle in Custom mode', () => {
  resetStore();
  usePipelineFormStore.getState().setFormField('pipelineMode', 'Custom');

  render(<AdvancedSettingsSection />);

  expect(
    screen.getByText('NeuroFLOW is available for built-in FreeSurfer/FastSurfer presets. Custom mode uses the standard runner.'),
  ).toBeInTheDocument();
  const toggle = screen.getByRole('checkbox', {name: /Use NeuroFLOW scheduler/i});
  expect(toggle).toBeDisabled();
  expect(toggle).not.toBeChecked();
  expect(screen.queryByText('Max parallel tasks')).not.toBeInTheDocument();
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
  expect(screen.getByText('Start safely, then scale up')).toBeInTheDocument();
  expect(screen.getByText('Max Retries Per Task')).toBeInTheDocument();
  expect(screen.getByText('Scheduling risk')).toBeInTheDocument();
  expect(screen.getByText('Max I/O-Heavy Tasks')).toBeInTheDocument();
  expect(screen.getByText('Machine Profile Identifier')).toBeInTheDocument();
  expect(screen.getByText('Remember memory failures')).toBeInTheDocument();
});

test('shows workspace-loaded helper text when max parallel tasks is 1', () => {
  resetStore();
  usePipelineFormStore.getState().setFormField('pipelineMode', 'FreeSurfer 8 + Volume');
  usePipelineFormStore.getState().setFormField('neuroflowEnabled', true);
  usePipelineFormStore.getState().setFormField('neuroflowMaxConcurrentTasks', 1);

  render(<AdvancedSettingsSection />);

  fireEvent.click(screen.getByRole('button', {name: /Show Settings/i}));

  expect(
    screen.getByText('Loaded from workspace. Use 2 or more for parallel scheduling.'),
  ).toBeInTheDocument();
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

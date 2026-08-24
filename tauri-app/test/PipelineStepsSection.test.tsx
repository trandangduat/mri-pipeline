import React from 'react';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {PipelineStepsSection} from '../src/pages/PipelinePage';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';

const mockMetadata = {
  version: 1,
  stages: [
    {id: 'reorientation', label: 'Reorientation, resize'},
    {id: 'brain_extraction', label: 'Brain Extraction'},
    {id: 'segmentation', label: 'Subcortical Segmentation'},
    {id: 'template_registration', label: 'Template Registration'},
    {id: 'bias_correction', label: 'Image standardization'},
    {id: 'white_matter_segmentation', label: 'WM Segmentation'},
    {id: 'surface_reconstruction', label: 'Surface Reconstruction'},
    {id: 'surface_registration', label: 'Surface Registration'},
    {id: 'stats_extraction', label: 'Statistics & Atlas mapping'},
  ],
  stage_order: [
    'reorientation',
    'brain_extraction',
    'segmentation',
    'template_registration',
    'bias_correction',
    'white_matter_segmentation',
    'surface_reconstruction',
    'surface_registration',
    'stats_extraction',
  ],
  tools: {
    cat12_volume_segmentation: {key: 'cat12_volume_segmentation', display_name: 'CAT12 Volume Segmentation'},
    cat12_volume_stats_extraction: {key: 'cat12_volume_stats_extraction', display_name: 'CAT12 Volume Stats'},
    cat12_full_segmentation: {key: 'cat12_full_segmentation', display_name: 'CAT12 Full Segmentation'},
    cat12_full_stats_extraction: {key: 'cat12_full_stats_extraction', display_name: 'CAT12 Full Stats'},
    fs8_reduced54_reorientation: {key: 'fs8_reduced54_reorientation', display_name: 'FS8 Reorientation'},
    synthseg_freesurfer_fs8: {key: 'synthseg_freesurfer_fs8', display_name: 'SynthSeg'},
    fs8_reduced54_stats: {key: 'fs8_reduced54_stats', display_name: 'FS8 Stats'},
  },
  tools_by_stage: {
    reorientation: ['fs8_reduced54_reorientation'],
    brain_extraction: [],
    segmentation: ['cat12_volume_segmentation', 'cat12_full_segmentation', 'synthseg_freesurfer_fs8'],
    template_registration: [],
    bias_correction: [],
    white_matter_segmentation: [],
    surface_reconstruction: [],
    surface_registration: [],
    stats_extraction: ['cat12_volume_stats_extraction', 'cat12_full_stats_extraction', 'fs8_reduced54_stats'],
  },
  pipeline_modes: [
    {id: 'CAT12 + Volume'},
    {id: 'CAT12 + Cortical Thickness'},
    {id: 'CAT12 + Volume + Cortical Thickness'},
    {id: 'FreeSurfer 8 + Volume'},
    {id: 'FreeSurfer 8 + Volume + Cortical Thickness'},
    {id: 'Custom'},
  ],
  presets: {
    'CAT12 + Volume': {
      tools: {
        reorientation: '',
        brain_extraction: '',
        segmentation: 'cat12_volume_segmentation',
        template_registration: '',
        bias_correction: '',
        white_matter_segmentation: '',
        surface_reconstruction: '',
        surface_registration: '',
        stats_extraction: 'cat12_volume_stats_extraction',
      },
      stats: ['subcortical_volume', 'cortical_volume'],
      default_atlases: {
        subcortical_volume: ['cat12_neuromorphometrics'],
        cortical_volume: ['cat12_schaefer2018_200parcels_17networks'],
      },
    },
    'CAT12 + Cortical Thickness': {
      tools: {
        reorientation: '',
        brain_extraction: '',
        segmentation: 'cat12_full_segmentation',
        template_registration: '',
        bias_correction: '',
        white_matter_segmentation: '',
        surface_reconstruction: '',
        surface_registration: '',
        stats_extraction: 'cat12_full_stats_extraction',
      },
      stats: ['cortical_thickness'],
      default_atlases: {
        cortical_thickness: ['aparc'],
      },
    },
    'CAT12 + Volume + Cortical Thickness': {
      tools: {
        reorientation: '',
        brain_extraction: '',
        segmentation: 'cat12_full_segmentation',
        template_registration: '',
        bias_correction: '',
        white_matter_segmentation: '',
        surface_reconstruction: '',
        surface_registration: '',
        stats_extraction: 'cat12_full_stats_extraction',
      },
      stats: ['subcortical_volume', 'cortical_volume', 'cortical_thickness'],
      default_atlases: {
        subcortical_volume: ['cat12_neuromorphometrics'],
        cortical_volume: ['cat12_schaefer2018_200parcels_17networks'],
        cortical_thickness: ['aparc'],
      },
    },
    'FreeSurfer 8 + Volume': {
      tools: {
        reorientation: 'fs8_reduced54_reorientation',
        brain_extraction: '',
        segmentation: 'synthseg_freesurfer_fs8',
        template_registration: '',
        bias_correction: '',
        white_matter_segmentation: '',
        surface_reconstruction: '',
        surface_registration: '',
        stats_extraction: 'fs8_reduced54_stats',
      },
      stats: ['subcortical_volume', 'cortical_volume'],
      default_atlases: {
        subcortical_volume: ['freesurfer_aseg'],
        cortical_volume: ['freesurfer_aparc'],
      },
    },
    'FreeSurfer 8 + Volume + Cortical Thickness': {
      tools: {
        reorientation: 'fs8_reduced54_reorientation',
        brain_extraction: '',
        segmentation: 'synthseg_freesurfer_fs8',
        template_registration: '',
        bias_correction: '',
        white_matter_segmentation: '',
        surface_reconstruction: '',
        surface_registration: '',
        stats_extraction: 'fs8_reduced54_stats',
      },
      stats: ['subcortical_volume', 'cortical_volume', 'cortical_thickness'],
      default_atlases: {
        subcortical_volume: ['freesurfer_aseg'],
        cortical_volume: ['freesurfer_aparc'],
        cortical_thickness: ['aparc'],
      },
    },
  },
  stats_vectors: {
    subcortical_volume: {
      key: 'subcortical_volume',
      label: 'Subcortical Volume',
      value_column: 'Volume_mm3',
      atlases: ['cat12_neuromorphometrics', 'freesurfer_aseg'],
    },
    cortical_volume: {
      key: 'cortical_volume',
      label: 'Cortical Volume',
      value_column: 'Volume_mm3',
      atlases: ['cat12_schaefer2018_200parcels_17networks', 'freesurfer_aparc'],
    },
    cortical_thickness: {
      key: 'cortical_thickness',
      label: 'Cortical Thickness',
      value_column: 'ThickAvg',
      atlases: ['aparc'],
    },
  },
  atlases: {
    cat12_neuromorphometrics: {key: 'cat12_neuromorphometrics', label: 'CAT12 Neuromorphometrics'},
    cat12_schaefer2018_200parcels_17networks: {key: 'cat12_schaefer2018_200parcels_17networks', label: 'CAT12 Schaefer 200'},
    freesurfer_aseg: {key: 'freesurfer_aseg', label: 'FreeSurfer Aseg'},
    freesurfer_aparc: {key: 'freesurfer_aparc', label: 'FreeSurfer Aparc'},
    aparc: {key: 'aparc', label: 'Desikan-Killiany (aparc)'},
  },
  tool_contracts: {
    fs8_reduced54_reorientation: {requires: [], produces: ['orig_mgz']},
    cat12_volume_segmentation: {requires: [], produces: ['cat12_seg']},
    cat12_full_segmentation: {requires: [], produces: ['cat12_seg']},
    cat12_volume_stats_extraction: {requires: ['cat12_seg'], produces: []},
    cat12_full_stats_extraction: {requires: ['cat12_seg'], produces: []},
    synthseg_freesurfer_fs8: {requires: [], produces: ['seg_synthseg_rca']},
    fs8_reduced54_stats: {requires: ['seg_synthseg_rca'], produces: []},
  },
};

vi.mock('../src/query/useEnvironment', () => ({
  useMetadata: () => ({
    data: mockMetadata,
    isLoading: false,
    isError: false,
  }),
  useClient: () => ({
    uploadLicense: vi.fn(),
  }),
}));

function renderPipelineSteps() {
  const queryClient = new QueryClient({
    defaultOptions: {queries: {retry: false}},
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PipelineStepsSection />
    </QueryClientProvider>,
  );
}

describe('PipelineStepsSection CAT12 preset display', () => {
  beforeEach(() => {
    usePipelineFormStore.getState().resetForm();
  });

  it('shows only CAT12 Processing and CAT12 Statistics for CAT12 + Volume preset', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'CAT12 + Volume',
      stage_segmentation: 'cat12_volume_segmentation',
      stage_stats_extraction: 'cat12_volume_stats_extraction',
    });

    renderPipelineSteps();

    // Built-in presets hide tools by default. Click Show Tools.
    await user.click(screen.getByRole('button', {name: /Show Tools/i}));

    expect(screen.getByText('CAT12 Processing')).toBeInTheDocument();
    expect(screen.getByText('CAT12 Statistics')).toBeInTheDocument();

    // Verify non-CAT12 stages are not displayed
    expect(screen.queryByText('Brain Extraction')).not.toBeInTheDocument();
    expect(screen.queryByText('Reorientation, resize')).not.toBeInTheDocument();
    expect(screen.queryByText('Template Registration')).not.toBeInTheDocument();
    expect(screen.queryByText('Image standardization')).not.toBeInTheDocument();
    expect(screen.queryByText('WM Segmentation')).not.toBeInTheDocument();
    expect(screen.queryByText('Surface Reconstruction')).not.toBeInTheDocument();
    expect(screen.queryByText('Surface Registration')).not.toBeInTheDocument();

    // Verify only the 2 stage selects are rendered (plus 1 preset select = 3 comboboxes total)
    const selects = screen.getAllByRole('combobox');
    expect(selects).toHaveLength(3);
    expect(screen.getByDisplayValue('CAT12 Volume Segmentation')).toBeInTheDocument();
    expect(screen.getByDisplayValue('CAT12 Volume Stats')).toBeInTheDocument();
  });

  it('shows only CAT12 Processing and CAT12 Statistics for CAT12 + Cortical Thickness preset', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'CAT12 + Cortical Thickness',
      stage_segmentation: 'cat12_full_segmentation',
      stage_stats_extraction: 'cat12_full_stats_extraction',
    });

    renderPipelineSteps();

    await user.click(screen.getByRole('button', {name: /Show Tools/i}));

    expect(screen.getByText('CAT12 Processing')).toBeInTheDocument();
    expect(screen.getByText('CAT12 Statistics')).toBeInTheDocument();
    expect(screen.queryByText('Brain Extraction')).not.toBeInTheDocument();

    const selects = screen.getAllByRole('combobox');
    expect(selects).toHaveLength(3);
    expect(screen.getByDisplayValue('CAT12 Full Segmentation')).toBeInTheDocument();
    expect(screen.getByDisplayValue('CAT12 Full Stats')).toBeInTheDocument();
  });

  it('shows full stage table with unavailable stages for FreeSurfer 8 + Volume', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'FreeSurfer 8 + Volume',
      stage_reorientation: 'fs8_reduced54_reorientation',
      stage_segmentation: 'synthseg_freesurfer_fs8',
      stage_stats_extraction: 'fs8_reduced54_stats',
      stage_brain_extraction: '',
      stage_template_registration: '',
      stage_bias_correction: '',
      stage_white_matter_segmentation: '',
      stage_surface_reconstruction: '',
      stage_surface_registration: '',
    });

    renderPipelineSteps();

    await user.click(screen.getByRole('button', {name: /Show Tools/i}));

    // Shows standard labels
    expect(screen.getByText('Reorientation, resize')).toBeInTheDocument();
    expect(screen.getByText('Brain Extraction')).toBeInTheDocument();
    expect(screen.getByText('Subcortical Segmentation')).toBeInTheDocument();
    expect(screen.getByText('Template Registration')).toBeInTheDocument();
    expect(screen.getByText('Statistics & Atlas mapping')).toBeInTheDocument();

    // CAT12 labels should not be present
    expect(screen.queryByText('CAT12 Processing')).not.toBeInTheDocument();
    expect(screen.queryByText('CAT12 Statistics')).not.toBeInTheDocument();

    // Full 9 stages + 1 preset select = 10 comboboxes
    const selects = screen.getAllByRole('combobox');
    expect(selects).toHaveLength(10);
  });

  it('preserves showTools toggle state when switching between presets', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'CAT12 + Volume',
      stage_segmentation: 'cat12_volume_segmentation',
      stage_stats_extraction: 'cat12_volume_stats_extraction',
    });

    renderPipelineSteps();

    // Initially tools are hidden
    expect(screen.queryByText('CAT12 Processing')).not.toBeInTheDocument();

    // User clicks Show Tools
    await user.click(screen.getByRole('button', {name: /Show Tools/i}));
    expect(screen.getByText('CAT12 Processing')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /Hide Tools/i})).toBeInTheDocument();

    // User switches preset to FreeSurfer 8 + Volume
    const presetSelect = screen.getByLabelText(/Pipeline preset/i);
    await user.selectOptions(presetSelect, 'FreeSurfer 8 + Volume');

    // Tools should still be visible (not automatically hidden)
    expect(screen.getByRole('button', {name: /Hide Tools/i})).toBeInTheDocument();
    expect(screen.getByText('Subcortical Segmentation')).toBeInTheDocument();

    // User switches preset to CAT12 + Cortical Thickness
    await user.selectOptions(presetSelect, 'CAT12 + Cortical Thickness');

    // Tools should still be visible
    expect(screen.getByRole('button', {name: /Hide Tools/i})).toBeInTheDocument();
    expect(screen.getByText('CAT12 Processing')).toBeInTheDocument();
  });

  it('preserves hidden tools state when switching between presets', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'CAT12 + Volume',
      stage_segmentation: 'cat12_volume_segmentation',
      stage_stats_extraction: 'cat12_volume_stats_extraction',
    });

    renderPipelineSteps();

    // Initially tools are hidden
    expect(screen.queryByText('CAT12 Processing')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: /Show Tools/i})).toBeInTheDocument();

    // User switches preset to FreeSurfer 8 + Volume
    const presetSelect = screen.getByLabelText(/Pipeline preset/i);
    await user.selectOptions(presetSelect, 'FreeSurfer 8 + Volume');

    // Tools should still be hidden
    expect(screen.queryByText('Subcortical Segmentation')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: /Show Tools/i})).toBeInTheDocument();
  });

  it('automatically shows tools when switching from a preset to Custom', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'CAT12 + Volume',
      stage_segmentation: 'cat12_volume_segmentation',
      stage_stats_extraction: 'cat12_volume_stats_extraction',
    });

    renderPipelineSteps();

    // Initially tools are hidden
    expect(screen.queryByText('CAT12 Processing')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: /Show Tools/i})).toBeInTheDocument();

    // User switches preset to Custom
    const presetSelect = screen.getByLabelText(/Pipeline preset/i);
    await user.selectOptions(presetSelect, 'Custom');

    // Tools should now be automatically shown
    expect(screen.getByRole('button', {name: /Hide Tools/i})).toBeInTheDocument();
    expect(screen.getByText('Subcortical Segmentation')).toBeInTheDocument();
  });

  it('defaults formValues.pipelineMode to FreeSurfer 8 + Volume + Cortical Thickness after resetForm', () => {
    usePipelineFormStore.getState().resetForm();
    expect(usePipelineFormStore.getState().formValues.pipelineMode).toBe('FreeSurfer 8 + Volume + Cortical Thickness');
  });

  it('applies default atlases and tools when a preset is selected', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'Custom',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: [],
      cortical_thickness: ['aparc'],
    });

    renderPipelineSteps();

    const presetSelect = screen.getByLabelText(/Pipeline preset/i);
    await user.selectOptions(presetSelect, 'CAT12 + Volume');

    const state = usePipelineFormStore.getState();
    expect(state.formValues.pipelineMode).toBe('CAT12 + Volume');
    expect(state.formValues.stage_segmentation).toBe('cat12_volume_segmentation');
    expect(state.formValues.stage_stats_extraction).toBe('cat12_volume_stats_extraction');
    expect(state.formValues.stage_reorientation).toBe('');

    expect(state.selectedStatsAtlases).toEqual({
      subcortical_volume: ['cat12_neuromorphometrics'],
      cortical_volume: ['cat12_schaefer2018_200parcels_17networks'],
      cortical_thickness: [],
    });
  });

  it('clears cortical_thickness atlases when switching from thickness preset to FreeSurfer 8 + Volume', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'CAT12 + Cortical Thickness',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: [],
      cortical_volume: [],
      cortical_thickness: ['aparc'],
    });

    renderPipelineSteps();

    const presetSelect = screen.getByLabelText(/Pipeline preset/i);
    await user.selectOptions(presetSelect, 'FreeSurfer 8 + Volume');

    const state = usePipelineFormStore.getState();
    expect(state.formValues.pipelineMode).toBe('FreeSurfer 8 + Volume');
    expect(state.selectedStatsAtlases.cortical_thickness).toEqual([]);
    expect(state.selectedStatsAtlases.subcortical_volume).toEqual(['freesurfer_aseg']);
    expect(state.selectedStatsAtlases.cortical_volume).toEqual(['freesurfer_aparc']);
  });

  it('switches pipelineMode to Custom when a stage tool is changed to a different tool or Not available', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'CAT12 + Volume',
      stage_segmentation: 'cat12_volume_segmentation',
      stage_stats_extraction: 'cat12_volume_stats_extraction',
    });

    renderPipelineSteps();

    await user.click(screen.getByRole('button', {name: /Show Tools/i}));

    // Change CAT12 Processing (segmentation) to Not available
    const segSelect = screen.getByDisplayValue('CAT12 Volume Segmentation');
    await user.selectOptions(segSelect, '');

    expect(usePipelineFormStore.getState().formValues.pipelineMode).toBe('Custom');
    expect(usePipelineFormStore.getState().formValues.stage_segmentation).toBe('');
  });

  it('keeps preset mode if stage tool change selects the same tool as the preset', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'CAT12 + Volume',
      stage_segmentation: 'cat12_volume_segmentation',
      stage_stats_extraction: 'cat12_volume_stats_extraction',
    });

    renderPipelineSteps();

    await user.click(screen.getByRole('button', {name: /Show Tools/i}));

    const segSelect = screen.getByDisplayValue('CAT12 Volume Segmentation');
    await user.selectOptions(segSelect, 'cat12_volume_segmentation');

    expect(usePipelineFormStore.getState().formValues.pipelineMode).toBe('CAT12 + Volume');
  });

  it('keeps pipelineMode as Custom when modifying stage tools in Custom mode', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'Custom',
      stage_segmentation: 'synthseg_freesurfer_fs8',
      stage_stats_extraction: 'fs8_reduced54_stats',
    });

    renderPipelineSteps();

    const segSelect = screen.getByDisplayValue('SynthSeg');
    await user.selectOptions(segSelect, 'cat12_volume_segmentation');

    expect(usePipelineFormStore.getState().formValues.pipelineMode).toBe('Custom');
    expect(usePipelineFormStore.getState().formValues.stage_segmentation).toBe('cat12_volume_segmentation');
  });
});

describe('PipelineStepsSection custom-mode tool compatibility', () => {
  beforeEach(() => {
    usePipelineFormStore.getState().resetForm();
  });

  it('shows a red error and highlights rows for an invalid Custom combo, clearing on preset switch', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'Custom',
      stage_reorientation: 'fs8_reduced54_reorientation',
      stage_stats_extraction: 'fs8_reduced54_stats',
    });

    const {container} = renderPipelineSteps();

    // FS8 stats needs SynthSeg RCA outputs which this selection cannot produce.
    expect(screen.getByText('Invalid tool combination')).toBeTruthy();
    const alert = container.querySelector('[role="alert"]');
    expect(alert!.className).toMatch(/rose-500|cursor-semantic-error/);
    expect(container.querySelector('.border-l-cursor-semantic-error')).not.toBeNull();

    // Switching to a named preset clears the error + highlights.
    const modeSelect = container.querySelector('#pipelineMode') as HTMLSelectElement | null;
    if (modeSelect) {
      await user.selectOptions(modeSelect, 'FreeSurfer 8 + Volume');
      expect(screen.queryByText('Invalid tool combination')).toBeNull();
      expect(container.querySelector('.border-l-cursor-semantic-error')).toBeNull();
    }
  });

  it('shows no error when a valid Custom combo is selected', () => {
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'Custom',
      stage_segmentation: 'cat12_volume_segmentation',
      stage_stats_extraction: 'cat12_volume_stats_extraction',
    });
    const {container} = renderPipelineSteps();
    expect(screen.queryByText('Invalid tool combination')).toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});

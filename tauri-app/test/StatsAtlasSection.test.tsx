import React from 'react';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {StatsAtlasSection} from '../src/pages/PipelinePage';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';

const mockMetadata = {
  version: 1,
  stages: [
    {id: 'segmentation', label: 'Subcortical Segmentation'},
    {id: 'stats_extraction', label: 'Statistics & Atlas mapping'},
  ],
  stage_order: ['segmentation', 'stats_extraction'],
  fs7_recon_style_stage_order: [],
  tools: {
    fs8_reduced54_stats: {key: 'fs8_reduced54_stats', display_name: 'FS8 Stats'},
    cat12_volume_stats_extraction: {key: 'cat12_volume_stats_extraction', display_name: 'CAT12 Volume Stats'},
  },
  tools_by_stage: {
    segmentation: [],
    stats_extraction: ['fs8_reduced54_stats', 'cat12_volume_stats_extraction'],
  },
  pipeline_modes: [
    {id: 'FreeSurfer 8 + Volume'},
    {id: 'FreeSurfer 8 + Volume + Cortical Thickness'},
    {id: 'CAT12 + Volume'},
    {id: 'Custom'},
  ],
  presets: {
    'FreeSurfer 8 + Volume': {
      tools: {
        segmentation: 'synthseg_freesurfer_fs8',
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
        segmentation: 'synthseg_freesurfer_fs8',
        stats_extraction: 'fs8_reduced54_stats',
      },
      stats: ['subcortical_volume', 'cortical_volume', 'cortical_thickness'],
      default_atlases: {
        subcortical_volume: ['freesurfer_aseg'],
        cortical_volume: ['freesurfer_aparc'],
        cortical_thickness: ['aparc'],
      },
    },
    'CAT12 + Volume': {
      tools: {
        segmentation: 'cat12_volume_segmentation',
        stats_extraction: 'cat12_volume_stats_extraction',
      },
      stats: ['subcortical_volume', 'cortical_volume'],
      default_atlases: {
        subcortical_volume: ['cat12_neuromorphometrics'],
        cortical_volume: ['cat12_schaefer2018_200parcels_17networks'],
      },
    },
  },
  stats_vectors: {
    subcortical_volume: {
      key: 'subcortical_volume',
      label: 'Subcortical Volume',
      value_column: 'Volume_mm3',
      atlases: ['freesurfer_aseg', 'cat12_neuromorphometrics', 'pauli_2017'],
    },
    cortical_volume: {
      key: 'cortical_volume',
      label: 'Cortical Volume',
      value_column: 'Volume_mm3',
      atlases: ['freesurfer_aparc', 'cat12_schaefer2018_200parcels_17networks'],
    },
    cortical_thickness: {
      key: 'cortical_thickness',
      label: 'Cortical Thickness',
      value_column: 'ThickAvg',
      atlases: ['aparc'],
    },
  },
  atlases: {
    freesurfer_aseg: {key: 'freesurfer_aseg', label: 'FreeSurfer Aseg'},
    cat12_neuromorphometrics: {key: 'cat12_neuromorphometrics', label: 'CAT12 Neuromorphometrics'},
    pauli_2017: {key: 'pauli_2017', label: 'Pauli Subcortical Atlas'},
    freesurfer_aparc: {key: 'freesurfer_aparc', label: 'FreeSurfer Aparc'},
    cat12_schaefer2018_200parcels_17networks: {key: 'cat12_schaefer2018_200parcels_17networks', label: 'CAT12 Schaefer 200'},
    aparc: {key: 'aparc', label: 'Desikan-Killiany (aparc)'},
  },
};

vi.mock('../src/query/useEnvironment', () => ({
  useMetadata: () => ({
    data: mockMetadata,
    isLoading: false,
    isError: false,
  }),
}));

function renderStatsAtlas() {
  const queryClient = new QueryClient({
    defaultOptions: {queries: {retry: false}},
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <StatsAtlasSection />
    </QueryClientProvider>,
  );
}

describe('StatsAtlasSection', () => {
  beforeEach(() => {
    usePipelineFormStore.getState().resetForm();
  });

  it('renders all three stats vector groups with chips and Add Atlas buttons', () => {
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: ['freesurfer_aparc'],
      cortical_thickness: ['aparc'],
    });

    renderStatsAtlas();

    expect(screen.getByText(/Subcortical Volume/)).toBeInTheDocument();
    expect(screen.getByText(/Cortical Volume/)).toBeInTheDocument();
    expect(screen.getByText(/Cortical Thickness/)).toBeInTheDocument();

    expect(screen.getByText('FreeSurfer Aseg')).toBeInTheDocument();
    expect(screen.getByText('FreeSurfer Aparc')).toBeInTheDocument();
    expect(screen.getByText('Desikan-Killiany (aparc)')).toBeInTheDocument();

    const addButtons = screen.getAllByRole('button', {name: /Add Atlas/i});
    expect(addButtons).toHaveLength(3);
    addButtons.forEach((btn) => expect(btn).toBeEnabled());
  });

  it('keeps preset mode when adding an atlas to a covered stats vector', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'FreeSurfer 8 + Volume',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: ['freesurfer_aparc'],
      cortical_thickness: [],
    });

    renderStatsAtlas();

    const addButtons = screen.getAllByRole('button', {name: /Add Atlas/i});
    // Click Add Atlas for Subcortical Volume (first button)
    await user.click(addButtons[0]);

    // In modal, click Pauli Subcortical Atlas to add it
    const pauliButton = screen.getByRole('button', {name: /Pauli Subcortical Atlas/i});
    await user.click(pauliButton);

    const state = usePipelineFormStore.getState();
    expect(state.formValues.pipelineMode).toBe('FreeSurfer 8 + Volume');
    expect(state.selectedStatsAtlases.subcortical_volume).toContain('pauli_2017');
    expect(state.selectedStatsAtlases.subcortical_volume).toContain('freesurfer_aseg');
  });

  it('switches to Custom mode when adding an atlas to an uncovered stats vector', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'FreeSurfer 8 + Volume',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: ['freesurfer_aparc'],
      cortical_thickness: [],
    });

    renderStatsAtlas();

    const addButtons = screen.getAllByRole('button', {name: /Add Atlas/i});
    // Click Add Atlas for Cortical Thickness (third button)
    await user.click(addButtons[2]);

    // Click Desikan-Killiany (aparc)
    const aparcButton = screen.getByRole('button', {name: /Desikan-Killiany \(aparc\)/i});
    await user.click(aparcButton);

    const state = usePipelineFormStore.getState();
    expect(state.formValues.pipelineMode).toBe('Custom');
    expect(state.selectedStatsAtlases.cortical_thickness).toContain('aparc');
  });

  it('switches to Custom mode when removing a preset default atlas from a covered stats vector', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'FreeSurfer 8 + Volume',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: ['freesurfer_aparc'],
      cortical_thickness: [],
    });

    renderStatsAtlas();

    // Click remove button on FreeSurfer Aseg chip
    const removeBtn = screen.getByRole('button', {name: /Remove atlas FreeSurfer Aseg/i});
    await user.click(removeBtn);

    const state = usePipelineFormStore.getState();
    expect(state.formValues.pipelineMode).toBe('Custom');
    expect(state.selectedStatsAtlases.subcortical_volume).not.toContain('freesurfer_aseg');
  });

  it('keeps preset mode when removing a non-default atlas from a covered stats vector', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'FreeSurfer 8 + Volume',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg', 'pauli_2017'],
      cortical_volume: ['freesurfer_aparc'],
      cortical_thickness: [],
    });

    renderStatsAtlas();

    // Remove Pauli Subcortical Atlas (which is not a preset default)
    const removeBtn = screen.getByRole('button', {name: /Remove atlas Pauli Subcortical Atlas/i});
    await user.click(removeBtn);

    const state = usePipelineFormStore.getState();
    expect(state.formValues.pipelineMode).toBe('FreeSurfer 8 + Volume');
    expect(state.selectedStatsAtlases.subcortical_volume).toEqual(['freesurfer_aseg']);
  });

  it('switches to Custom mode when removing a default atlas via the modal picker', async () => {
    const user = userEvent.setup();
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'FreeSurfer 8 + Volume',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: ['freesurfer_aparc'],
      cortical_thickness: [],
    });

    renderStatsAtlas();

    const addButtons = screen.getAllByRole('button', {name: /Add Atlas/i});
    // Open Subcortical Volume modal picker
    await user.click(addButtons[0]);

    // Click FreeSurfer Aseg (which is currently selected) to deselect it
    const asegButton = screen.getByRole('button', {name: /freesurfer_aseg/i});
    await user.click(asegButton);

    const state = usePipelineFormStore.getState();
    expect(state.formValues.pipelineMode).toBe('Custom');
    expect(state.selectedStatsAtlases.subcortical_volume).not.toContain('freesurfer_aseg');
  });

  it('shows unavailable warning in Custom mode when stats vector has atlases and stage_stats_extraction is Not available', () => {
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'Custom',
      stage_stats_extraction: '',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: [],
      cortical_thickness: [],
    });

    renderStatsAtlas();

    // Warning should be present under Subcortical Volume
    const warning = screen.getByText('This stats vector has selected atlases, but Statistics & Atlas mapping is set to Not available.');
    expect(warning).toBeInTheDocument();
  });

  it('does not show unavailable warning when stage_stats_extraction is configured', () => {
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'Custom',
      stage_stats_extraction: 'fs8_reduced54_stats',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: [],
      cortical_thickness: [],
    });

    renderStatsAtlas();

    expect(screen.queryByText(/Statistics & Atlas mapping is set to Not available/i)).not.toBeInTheDocument();
  });

  it('does not show unavailable warning in a preset mode', () => {
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'FreeSurfer 8 + Volume',
      stage_stats_extraction: '',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: [],
      cortical_thickness: [],
    });

    renderStatsAtlas();

    expect(screen.queryByText(/Statistics & Atlas mapping is set to Not available/i)).not.toBeInTheDocument();
  });

  it('does not show unavailable warning when stats vector has no selected atlases', () => {
    usePipelineFormStore.getState().setFormFields({
      pipelineMode: 'Custom',
      stage_stats_extraction: '',
    });
    usePipelineFormStore.getState().setSelectedStatsAtlases({
      subcortical_volume: [],
      cortical_volume: [],
      cortical_thickness: [],
    });

    renderStatsAtlas();

    expect(screen.queryByText(/Statistics & Atlas mapping is set to Not available/i)).not.toBeInTheDocument();
  });
});

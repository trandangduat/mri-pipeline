import {describe, expect, it} from 'vitest';
import {
  isPresetDefaultAtlas,
  isPresetMode,
  presetDefaultAtlases,
  presetHandlesStat,
} from '../src/lib/pipelinePresets';
import type {AppMetadata} from '../src/types/backend';

const mockMetadata = {
  version: 1,
  project_root: '/root',
  pipeline_modes: [
    {id: 'FreeSurfer 8 + Volume', aliases: [], tools: {}, stats: ['subcortical_volume', 'cortical_volume']},
    {id: 'CAT12 + Volume', aliases: [], tools: {}, stats: ['subcortical_volume', 'cortical_volume']},
    {id: 'Custom', aliases: [], tools: {}, stats: []},
  ],
  presets: {
    'FreeSurfer 8 + Volume': {
      tools: {segmentation: 'synthseg_freesurfer_fs8'},
      stats: ['subcortical_volume', 'cortical_volume'],
      default_atlases: {
        subcortical_volume: ['freesurfer_aseg'],
        cortical_volume: ['freesurfer_aparc'],
      },
    },
    'CAT12 + Volume': {
      tools: {segmentation: 'cat12_volume_segmentation'},
      stats: ['subcortical_volume', 'cortical_volume'],
      default_atlases: {
        subcortical_volume: ['cat12_neuromorphometrics'],
        cortical_volume: ['cat12_schaefer2018_200parcels_17networks'],
      },
    },
  },
  stages: [],
  stage_order: ['segmentation', 'stats_extraction'],
  fs7_recon_style_stage_order: [],
  tools: {},
  tools_by_stage: {},
  export_items: {},
  export_defaults: {},
  stats_vectors: {
    subcortical_volume: {key: 'subcortical_volume', label: 'Subcortical Volume', value_column: 'Volume_mm3', atlases: ['freesurfer_aseg', 'cat12_neuromorphometrics']},
    cortical_volume: {key: 'cortical_volume', label: 'Cortical Volume', value_column: 'Volume_mm3', atlases: ['freesurfer_aparc', 'cat12_schaefer2018_200parcels_17networks']},
    cortical_thickness: {key: 'cortical_thickness', label: 'Cortical Thickness', value_column: 'ThickAvg', atlases: ['aparc']},
  },
  atlases: {},
  vector_specs: {},
} as unknown as AppMetadata;

describe('pipelinePresets helpers', () => {
  it('presetDefaultAtlases returns preset default atlases and empty arrays for unhandled stats', () => {
    const fsDefaults = presetDefaultAtlases(mockMetadata, 'FreeSurfer 8 + Volume');
    expect(fsDefaults).toEqual({
      subcortical_volume: ['freesurfer_aseg'],
      cortical_volume: ['freesurfer_aparc'],
      cortical_thickness: [],
    });

    const catDefaults = presetDefaultAtlases(mockMetadata, 'CAT12 + Volume');
    expect(catDefaults).toEqual({
      subcortical_volume: ['cat12_neuromorphometrics'],
      cortical_volume: ['cat12_schaefer2018_200parcels_17networks'],
      cortical_thickness: [],
    });
  });

  it('presetDefaultAtlases safely handles null or missing presets', () => {
    expect(presetDefaultAtlases(null, 'FreeSurfer 8 + Volume')).toEqual({});
    expect(presetDefaultAtlases(mockMetadata, 'Custom')).toEqual({
      subcortical_volume: [],
      cortical_volume: [],
      cortical_thickness: [],
    });
  });

  it('isPresetMode detects valid presets vs Custom', () => {
    expect(isPresetMode(mockMetadata, 'FreeSurfer 8 + Volume')).toBe(true);
    expect(isPresetMode(mockMetadata, 'CAT12 + Volume')).toBe(true);
    expect(isPresetMode(mockMetadata, 'Custom')).toBe(false);
    expect(isPresetMode(mockMetadata, 'Nonexistent')).toBe(false);
    expect(isPresetMode(null, 'FreeSurfer 8 + Volume')).toBe(false);
  });

  it('presetHandlesStat checks if a preset handles a stats vector', () => {
    expect(presetHandlesStat(mockMetadata, 'FreeSurfer 8 + Volume', 'subcortical_volume')).toBe(true);
    expect(presetHandlesStat(mockMetadata, 'FreeSurfer 8 + Volume', 'cortical_volume')).toBe(true);
    expect(presetHandlesStat(mockMetadata, 'FreeSurfer 8 + Volume', 'cortical_thickness')).toBe(false);
    expect(presetHandlesStat(mockMetadata, 'Custom', 'subcortical_volume')).toBe(false);
  });

  it('isPresetDefaultAtlas checks if an atlas is a preset default', () => {
    expect(isPresetDefaultAtlas(mockMetadata, 'FreeSurfer 8 + Volume', 'subcortical_volume', 'freesurfer_aseg')).toBe(true);
    expect(isPresetDefaultAtlas(mockMetadata, 'FreeSurfer 8 + Volume', 'subcortical_volume', 'cat12_neuromorphometrics')).toBe(false);
    expect(isPresetDefaultAtlas(mockMetadata, 'FreeSurfer 8 + Volume', 'cortical_thickness', 'aparc')).toBe(false);
  });
});

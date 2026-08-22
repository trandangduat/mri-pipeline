import {describe, expect, it} from 'vitest';
import {validateSelectedTools, validateStageTools} from '../src/lib/stageValidation';
import type {AppMetadata} from '../src/types/backend';

const STAGES = [
  'reorientation',
  'brain_extraction',
  'segmentation',
  'template_registration',
  'bias_correction',
  'white_matter_segmentation',
  'surface_reconstruction',
  'surface_registration',
  'stats_extraction',
];

function emptyMap(): Record<string, string> {
  return Object.fromEntries(STAGES.map((stage) => [stage, '']));
}

export const validationMetadata = {
  stage_order: STAGES,
  fs7_recon_style_stage_order: [
    'reorientation',
    'template_registration',
    'brain_extraction',
    'segmentation',
    'bias_correction',
    'white_matter_segmentation',
    'surface_reconstruction',
    'surface_registration',
    'stats_extraction',
  ],
  tools: {
    fastsurfer_reorientation: {key: 'fastsurfer_reorientation', display_name: 'FastSurfer Reorientation'},
    fastsurfer_segmentation: {key: 'fastsurfer_segmentation', display_name: 'FastSurfer Segmentation'},
    fastsurfer_stats_extraction: {key: 'fastsurfer_stats_extraction', display_name: 'FastSurfer Stats'},
    fs8_reduced54_stats: {key: 'fs8_reduced54_stats', display_name: 'FS8 Stats'},
    cat12_volume_segmentation: {key: 'cat12_volume_segmentation', display_name: 'CAT12 Volume Segmentation'},
    cat12_volume_stats_extraction: {key: 'cat12_volume_stats_extraction', display_name: 'CAT12 Volume Stats'},
  },
  presets: {
    'CAT12 + Volume': {
      tools: {
        ...emptyMap(),
        segmentation: 'cat12_volume_segmentation',
        stats_extraction: 'cat12_volume_stats_extraction',
      },
      stats: [],
    },
  },
  tool_contracts: {
    fastsurfer_reorientation: {requires: [], produces: ['orig_mgz']},
    fastsurfer_segmentation: {requires: ['orig_mgz'], produces: ['seg_fastsurfer']},
    fastsurfer_stats_extraction: {
      requires: ['surfaces_final', 'sphere_reg', 'dkt_annots'],
      produces: ['stats_tsvs'],
    },
    fs8_reduced54_stats: {requires: ['seg_synthseg_rca'], produces: ['stats_tsvs']},
  },
} as unknown as AppMetadata;

describe('validateStageTools', () => {
  it('returns no violations for named preset modes', () => {
    const formValues = {pipelineMode: 'CAT12 + Volume'} as never;
    expect(validateStageTools(validationMetadata, formValues)).toEqual([]);
  });

  it('short-circuits a Custom map identical to a named preset', () => {
    const formValues = {
      pipelineMode: 'Custom',
      stage_segmentation: 'cat12_volume_segmentation',
      stage_stats_extraction: 'cat12_volume_stats_extraction',
    } as never;
    expect(validateStageTools(validationMetadata, formValues)).toEqual([]);
  });

  it('flags cross-family stats hazard in Custom mode', () => {
    const selected = {
      reorientation: 'fastsurfer_reorientation',
      segmentation: 'fastsurfer_segmentation',
      stats_extraction: 'fs8_reduced54_stats',
    };
    const violations = validateSelectedTools(validationMetadata, selected);
    expect(violations.map((v) => v.stageId)).toEqual(['stats_extraction']);
    expect(violations[0].missing).toContain('seg_synthseg_rca');
    expect(violations[0].reason).toContain('cannot run');
  });

  it('cascades violations when an upstream producer is disabled', () => {
    const selected = {
      segmentation: 'fastsurfer_segmentation',
      stats_extraction: 'fastsurfer_stats_extraction',
    };
    const violations = validateSelectedTools(validationMetadata, selected);
    // segmentation fails (no orig producer) -> stats fails (no surfaces/spheres)
    expect(violations.map((v) => v.stageId)).toEqual(['segmentation', 'stats_extraction']);
  });

  it('reports a single violation when nothing is selected', () => {
    const violations = validateSelectedTools(validationMetadata, {});
    expect(violations).toHaveLength(1);
    expect(violations[0].stageId).toBe('*');
  });
});

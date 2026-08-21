import {beforeEach, describe, expect, it} from 'vitest';
import {buildRunConfig, DEFAULT_FORM_VALUES, selectedToolsFromForm} from '../src/api/runConfig';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';

describe('workspace run config', () => {
  beforeEach(() => {
    usePipelineFormStore.getState().resetForm();
  });

  it('builds selected tools from stage fields when preset metadata is unavailable', () => {
    const config = buildRunConfig(
      {
        ...DEFAULT_FORM_VALUES,
        pipelineMode: 'FreeSurfer 8 + Volume + Cortical Thickness',
        stage_reorientation: 'fs8_reduced54_reorientation',
        stage_stats_extraction: 'fs8_reduced54_stats',
      },
      null,
    );

    expect(config.pipeline_mode).toBe('FreeSurfer 8 + Volume + Cortical Thickness');
    expect(config.selected_tools).toEqual({
      reorientation: 'fs8_reduced54_reorientation',
      stats_extraction: 'fs8_reduced54_stats',
    });
  });

  it('keeps workspace tools for non-custom workspace modes', () => {
    usePipelineFormStore.getState().applyWorkspaceConfig({
      pipeline_mode: 'FreeSurfer 8 + Volume + Cortical Thickness',
      tools: {
        reorientation: 'fs8_reduced54_reorientation',
        stats_extraction: 'fs8_reduced54_stats',
      },
      neuroflow_enabled: true,
      neuroflow_max_concurrent_tasks: 5,
    });

    const formValues = usePipelineFormStore.getState().formValues;

    expect(formValues.pipelineMode).toBe('FreeSurfer 8 + Volume + Cortical Thickness');
    expect(formValues.neuroflowEnabled).toBe(true);
    expect(formValues.neuroflowMaxConcurrentTasks).toBe(5);
    expect(selectedToolsFromForm(formValues)).toEqual({
      reorientation: 'fs8_reduced54_reorientation',
      stats_extraction: 'fs8_reduced54_stats',
    });
  });
});

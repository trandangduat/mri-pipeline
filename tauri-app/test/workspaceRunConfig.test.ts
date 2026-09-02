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

  it('serializes server_output_dir when runtime target is Server', () => {
    const configServer = buildRunConfig(
      {
        ...DEFAULT_FORM_VALUES,
        runtimeTarget: 'Server',
        outputDir: '/home/user/custom-outputs',
      },
      null,
    );
    expect(configServer.server_output_dir).toBe('/home/user/custom-outputs');

    const configLocal = buildRunConfig(
      {
        ...DEFAULT_FORM_VALUES,
        runtimeTarget: 'Local',
        outputDir: '/home/user/local-outputs',
      },
      null,
    );
    expect(configLocal.server_output_dir).toBe('');
  });

  it('populates inputServerDir and serverOutputDir when loading a server workspace with input_path and output_dir', () => {
    usePipelineFormStore.getState().applyWorkspaceConfig({
      input_source: 'Server',
      input_mode: 'batch_folder',
      input_path: '/home/catcd1/ADNIDOD_T1/ADNIDOD/',
      output_dir: '/home/catcd1/neuroflow-benchmark/outputs/30subjects_20parallel',
      server_output_dir: '',
      input_server_dir: '',
      run_target: 'Server',
    });

    const formValues = usePipelineFormStore.getState().formValues;
    expect(formValues.inputSource).toBe('Server');
    expect(formValues.inputServerDir).toBe('/home/catcd1/ADNIDOD_T1/ADNIDOD/');
    expect(formValues.serverOutputDir).toBe('/home/catcd1/neuroflow-benchmark/outputs/30subjects_20parallel');
  });
});

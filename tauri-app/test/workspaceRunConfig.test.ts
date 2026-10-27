import {beforeEach, describe, expect, it} from 'vitest';
import {buildExportConfig, buildRunConfig, DEFAULT_FORM_VALUES, selectedToolsFromForm} from '../src/api/runConfig';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';

describe('workspace run config', () => {
  beforeEach(() => {
    usePipelineFormStore.getState().resetForm();
  });

  it('preserves export options when saving and loading a workspace', () => {
    const names = {'reorientation.primary': 'scan.v2'};
    const forms = {...DEFAULT_FORM_VALUES, exportEnabled: false, exportFolder: 'custom',
      exportDefaultFormat: '.mgz', exportCustomNames: names, exportCustomFormats: {'segmentation.primary': 'same'}};
    const saved = JSON.parse(JSON.stringify({export_config: buildExportConfig(forms)}));
    usePipelineFormStore.getState().applyWorkspaceConfig(saved);
    const config = buildRunConfig(usePipelineFormStore.getState().formValues, null);
    expect(config.export_config).toEqual(saved.export_config);
    expect((config.export_config as {names: unknown}).names).toEqual(names);
  });

  it('resets export settings when a legacy workspace has none', () => {
    usePipelineFormStore.getState().setFormFields({exportEnabled: false, exportFolder: 'previous',
      exportCustomNames: {'reorientation.primary': 'previous'}, exportCustomFormats: {'reorientation.primary': '.mgz'}});
    usePipelineFormStore.getState().applyWorkspaceConfig({});
    expect(buildExportConfig(usePipelineFormStore.getState().formValues)).toEqual(buildExportConfig(DEFAULT_FORM_VALUES));
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

  it('keeps B6 as the default and preserves explicit baseline stage choices', () => {
    expect(buildRunConfig(DEFAULT_FORM_VALUES, null).neuroflow_policy).toBe('B6');
    const defaults = '{"reorient_resize":"cpu_1"}';
    usePipelineFormStore.getState().applyWorkspaceConfig({
      neuroflow_policy: 'B0', neuroflow_default_configurations: defaults,
    });
    const config = buildRunConfig(usePipelineFormStore.getState().formValues, null);
    expect(config.neuroflow_policy).toBe('B0');
    expect(config.neuroflow_default_configurations).toBe(defaults);
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

  it.each(['Local', 'Server'] as const)(
    'keeps local input separate from server staging when loading a %s runtime workspace',
    (runtimeTarget) => {
      usePipelineFormStore.getState().applyWorkspaceConfig({
        input_source: 'Local',
        run_target: runtimeTarget,
        input_mode: 'file',
        input_path: '/local/mri/scan.mgz',
        input_server_dir: '/server/staging',
        output_dir: '/outputs',
      });

      const formValues = usePipelineFormStore.getState().formValues;
      expect(formValues.inputPath).toBe('/local/mri/scan.mgz');
      expect(formValues.inputServerDir).toBe('/server/staging');
      const request = buildRunConfig(formValues, null);
      expect(request.input_source).toBe('Local');
      expect(request.run_target).toBe(runtimeTarget);
      expect(request.input_path).toBe('/local/mri/scan.mgz');
      expect(request.input_server_dir).toBe('/server/staging');
    },
  );

  it('does not use server staging as a missing local input', () => {
    usePipelineFormStore.getState().applyWorkspaceConfig({
      input_source: 'Local', run_target: 'Server',
      input_path: '', input_server_dir: '/server/staging',
    });

    const formValues = usePipelineFormStore.getState().formValues;
    expect(formValues.inputPath).toBe('');
    expect(formValues.inputServerDir).toBe('/server/staging');
    expect(buildRunConfig(formValues, null).input_path).toBe('');
  });

  it('does not use a local input as a missing server staging directory', () => {
    usePipelineFormStore.getState().applyWorkspaceConfig({
      input_source: 'Local', run_target: 'Server',
      input_path: '/local/mri/scan.mgz', input_server_dir: '',
    });

    const formValues = usePipelineFormStore.getState().formValues;
    expect(formValues.inputPath).toBe('/local/mri/scan.mgz');
    expect(formValues.inputServerDir).toBe('');
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

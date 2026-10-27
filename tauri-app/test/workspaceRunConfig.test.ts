import {beforeEach, describe, expect, it} from 'vitest';
import {buildExportConfig, buildRunConfig, DEFAULT_FORM_VALUES, selectedToolsFromForm} from '../src/api/runConfig';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';

describe('workspace run config', () => {
  beforeEach(() => {
    usePipelineFormStore.getState().resetForm();
  });

  it('sends the newly selected Server file after loading an old workspace', () => {
    usePipelineFormStore.getState().applyWorkspaceConfig({
      input_source: 'Server', run_target: 'Server', input_mode: 'file',
      input_path: '/old/A.nii.gz', input_server_dir: '/old/A.nii.gz',
    });
    usePipelineFormStore.getState().setFormField('inputServerDir', '/new/B.nii.gz');
    const form = usePipelineFormStore.getState().formValues;
    expect(form.inputPath).toBe('/old/A.nii.gz');
    expect(form.inputServerDir).toBe('/new/B.nii.gz');
    expect(buildRunConfig(form, null).input_path).toBe('/new/B.nii.gz');
  });

  it('does not fall back to a hidden old path when Server input is cleared', () => {
    expect(buildRunConfig({...DEFAULT_FORM_VALUES, inputSource: 'Server', runtimeTarget: 'Server',
      inputPath: '/old/A.nii.gz', inputServerDir: ''}, null).input_path).toBe('');
  });

  it.each(['Local', 'Server'] as const)('clears old Batch selections when the %s input folder changes', (inputSource) => {
    for (const bulk of [false, true]) {
      usePipelineFormStore.getState().resetForm();
      usePipelineFormStore.getState().setFormFields({inputSource, runtimeTarget: 'Server', inputMode: 'batch_folder',
        inputPath: '/old/local', inputServerDir: '/old/server', additionalInputPaths: '/old/A.nii.gz',
        batchImageCount: 1, batchScanMode: 'recursive'});
      usePipelineFormStore.getState().setPreparedRequest({input_files: ['/old/A.nii.gz']});
      const field = inputSource === 'Server' ? 'inputServerDir' : 'inputPath';
      if (bulk) usePipelineFormStore.getState().setFormFields({[field]: '/new/folder'});
      else usePipelineFormStore.getState().setFormField(field, '/new/folder');
      const form = usePipelineFormStore.getState().formValues;
      expect(form.additionalInputPaths).toBe('');
      expect(form.batchImageCount).toBeUndefined();
      expect(form.batchScanMode).toBeUndefined();
      expect(usePipelineFormStore.getState().preparedRequest).toBeNull();
      const request = buildRunConfig(form, null);
      expect(request.input_path).toBe('/new/folder');
      expect(request.selected_files).toEqual([]);
    }
  });

  it.each(['Local', 'Server'] as const)('clears old Batch selections when switching away from %s', (inputSource) => {
    for (const bulk of [false, true]) {
      usePipelineFormStore.getState().resetForm();
      usePipelineFormStore.getState().setFormFields({inputSource, runtimeTarget: 'Server', inputMode: 'batch_folder',
        inputPath: '/local/input', inputServerDir: '/server/input', additionalInputPaths: '/old/A.nii.gz',
        batchImageCount: 1, batchScanMode: 'recursive'});
      const nextSource = inputSource === 'Local' ? 'Server' : 'Local';
      if (bulk) usePipelineFormStore.getState().setFormFields({inputSource: nextSource});
      else usePipelineFormStore.getState().setFormField('inputSource', nextSource);
      const form = usePipelineFormStore.getState().formValues;
      expect(form.additionalInputPaths).toBe('');
      expect(form.batchImageCount).toBeUndefined();
      expect(form.batchScanMode).toBeUndefined();
      expect(buildRunConfig(form, null).input_path).toBe(nextSource === 'Server' ? '/server/input' : '/local/input');
    }
  });

  it('keeps Local Batch selections when only Server staging changes', () => {
    usePipelineFormStore.getState().setFormFields({inputSource: 'Local', runtimeTarget: 'Server', inputMode: 'batch_folder',
      inputPath: '/local/input', inputServerDir: '/old/staging', additionalInputPaths: '/local/input/A.nii.gz',
      batchImageCount: 1, batchScanMode: 'recursive'});
    usePipelineFormStore.getState().setFormField('inputServerDir', '/new/staging');
    const form = usePipelineFormStore.getState().formValues;
    const config = buildRunConfig(form, null);
    expect(form.batchImageCount).toBe(1);
    expect(form.batchScanMode).toBe('recursive');
    expect(config.input_path).toBe('/local/input');
    expect(config.input_server_dir).toBe('/new/staging');
    expect(config.selected_files).toEqual(['/local/input/A.nii.gz']);
  });

  it('keeps valid selections when the input is unchanged or explicitly replaced together', () => {
    usePipelineFormStore.getState().setFormFields({inputSource: 'Server', inputMode: 'batch_folder', inputPath: '',
      inputServerDir: '/old', additionalInputPaths: '/old/A.nii.gz', batchImageCount: 1});
    usePipelineFormStore.getState().setFormField('inputServerDir', '/old');
    expect(usePipelineFormStore.getState().formValues.additionalInputPaths).toBe('/old/A.nii.gz');
    usePipelineFormStore.getState().setFormFields({inputServerDir: '/new',
      additionalInputPaths: '/new/B.nii.gz', batchImageCount: 1, batchScanMode: 'recursive'});
    const form = usePipelineFormStore.getState().formValues;
    expect(form.batchImageCount).toBe(1);
    expect(buildRunConfig(form, null).selected_files).toEqual(['/new/B.nii.gz']);
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
    expect(buildRunConfig(formValues, null).input_path).toBe('/home/catcd1/ADNIDOD_T1/ADNIDOD/');
    expect(formValues.serverOutputDir).toBe('/home/catcd1/neuroflow-benchmark/outputs/30subjects_20parallel');
  });
});

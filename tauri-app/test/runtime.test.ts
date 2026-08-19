import {expect, test} from 'vitest';
import {currentTargetHardware, runtimeWarnings} from '../src/lib/runtime';

test('currentTargetHardware reads local environment hardware', () => {
  const hardware = currentTargetHardware({
    runtimeTarget: 'Local',
    environment: {
      ok: true,
      python: {ok: true, path: '', version: ''},
      docker: {ok: true, path: ''},
      ssh: {ok: true, path: ''},
      hardware: {hostname: '', logical_cores: 8, physical_cores: 8, total_ram_bytes: 17179869184},
    },
    remoteResult: {},
  });
  expect(hardware.label).toBe('Local');
  expect(hardware.connected).toBe(true);
  expect(hardware.logicalCores).toBe(8);
  expect(hardware.totalRamBytes).toBe(17179869184);
});

test('currentTargetHardware reads remote hardware when Server target', () => {
  const hardware = currentTargetHardware({
    runtimeTarget: 'Server',
    environment: undefined,
    remoteResult: {connected: true, hardware: {hostname: 'server', logical_cores: 32, total_ram_bytes: 68719476736}},
  });
  expect(hardware.label).toBe('Server');
  expect(hardware.connected).toBe(true);
  expect(hardware.logicalCores).toBe(32);
});

test('currentTargetHardware reports disconnected Server', () => {
  const hardware = currentTargetHardware({
    runtimeTarget: 'Server',
    environment: undefined,
    remoteResult: {connected: false},
  });
  expect(hardware.connected).toBe(false);
  expect(hardware.logicalCores).toBe(null);
});

test('runtimeWarnings flags threads above 90% of max', () => {
  const warnings = runtimeWarnings({
    runtimeTarget: 'Local',
    hardware: {label: 'Local', logicalCores: 8, totalRamBytes: null, connected: true},
    cpuThreads: 8,
    ramPercent: 40,
  });
  expect(warnings.length).toBe(1);
  expect(warnings[0]).toMatch(/CPU threads 8/);
});

test('runtimeWarnings flags RAM above 90%', () => {
  const warnings = runtimeWarnings({
    runtimeTarget: 'Local',
    hardware: {label: 'Local', logicalCores: 8, totalRamBytes: null, connected: true},
    cpuThreads: 2,
    ramPercent: 95,
  });
  expect(warnings.length).toBe(1);
  expect(warnings[0]).toMatch(/RAM 95%/);
});

test('runtimeWarnings flags disconnected server target', () => {
  const warnings = runtimeWarnings({
    runtimeTarget: 'Server',
    hardware: {label: 'Server', logicalCores: null, totalRamBytes: null, connected: false},
    cpuThreads: 2,
    ramPercent: 50,
  });
  expect(warnings.some((w) => w.includes('SSH is not connected'))).toBe(true);
});

test('runtimeWarnings is empty for a healthy local config', () => {
  const warnings = runtimeWarnings({
    runtimeTarget: 'Local',
    hardware: {label: 'Local', logicalCores: 16, totalRamBytes: null, connected: true},
    cpuThreads: 4,
    ramPercent: 50,
  });
  expect(warnings).toEqual([]);
});

test('applyWorkspaceConfig normalizes workspace settings, inputMode, and batch fields', async () => {
  const {usePipelineFormStore} = await import('../src/stores/pipelineFormStore');
  const store = usePipelineFormStore.getState();

  store.applyWorkspaceConfig({
    pipeline_mode: 'FastSurfer',
    input_source: 'Local',
    input_mode: 'dir',
    input_path: '/path/to/folder',
    selected_files: ['/path/to/folder/a.nii.gz', '/path/to/folder/b.nii.gz'],
    batch_image_count: 2,
    batch_scan_mode: 'recursive',
    output_dir: '/path/to/output',
    run_target: 'Local',
  });

  const values = usePipelineFormStore.getState().formValues;
  expect(values.pipelineMode).toBe('FastSurfer');
  expect(values.inputMode).toBe('batch_folder');
  expect(values.inputPath).toBe('/path/to/folder');
  expect(values.outputDir).toBe('/path/to/output');
  expect(values.additionalInputPaths).toBe('/path/to/folder/a.nii.gz, /path/to/folder/b.nii.gz');
  expect(values.batchImageCount).toBe(2);
  expect(values.batchScanMode).toBe('recursive');
});


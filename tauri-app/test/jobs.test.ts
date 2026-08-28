import {expect, test} from 'vitest';
import {
  jobProgress,
  extractOutputFiles,
  filterLogLines,
  progressStepEvents,
  stepEventState,
  dotClassForState,
  sidebarDotClass,
  displayJobState,
  deriveBatchImages,
  deriveBatchSummary,
  deriveImageSteps,
  deriveMetricsSeries,
  isEventForImage,
  deriveSubjectLabel,
  sanitizeTerminalLog,
  deriveJobDisplayMetadata,
  deriveSubjectStageInfo,
} from '../src/lib/jobs';

test('deriveSubjectLabel extracts parent folder for generic filenames like 001.mgz', () => {
  const res1 = deriveSubjectLabel('/home/catcd1/mri-remote-jobs/ADNI_011_S_8241_MR_MPR/001.mgz', 1);
  expect(res1.subject_id).toBe('ADNI_011_S_8241_MR_MPR');
  expect(res1.filename).toBe('001.mgz');

  const res2 = deriveSubjectLabel('/data/subject_42.nii.gz', 2);
  expect(res2.subject_id).toBe('subject_42');
  expect(res2.filename).toBe('subject_42.nii.gz');
});

test('sanitizeTerminalLog strips MRI_EVENT JSON transport lines unless showRaw is true', () => {
  const rawLog = '[14:28:03] Background job started\nMRI_EVENT {"kind": "progress"}\n[14:28:04] Image 1 done';
  const clean = sanitizeTerminalLog(rawLog, false);
  expect(clean).toContain('[14:28:03] Background job started');
  expect(clean).toContain('[14:28:04] Image 1 done');
  expect(clean).not.toContain('MRI_EVENT');

  const raw = sanitizeTerminalLog(rawLog, true);
  expect(raw).toContain('MRI_EVENT');
});

test('deriveJobDisplayMetadata provides fallbacks for started_at, duration, and output_dir', () => {
  const job = {
    state: 'completed',
    remote_job_dir: '/workspace/job_123',
    input_files: ['/data/ADNI_001/001.mgz'],
  };
  const events = [
    {kind: 'progress', time: 1700000000},
    {kind: 'progress', time: 1700000100},
  ];

  const meta = deriveJobDisplayMetadata(job, events);
  expect(meta.status_reconciled).toBe('completed');
  expect(meta.output_dir_str).toBe('/workspace/job_123');
  expect(meta.input_path_str).toBe('/data/ADNI_001/001.mgz');
  expect(meta.started_at_str).not.toBe('Unknown');
});

test('jobProgress maps states to percentages', () => {
  expect(jobProgress('completed', 0)).toBe(100);
  expect(jobProgress('running', 0)).toBe(10);
  expect(jobProgress('running', 5)).toBe(75);
  expect(jobProgress('running', 100)).toBe(90);
  expect(jobProgress('failed', 4)).toBe(0);
});

test('extractOutputFiles flattens event outputs', () => {
  const events = [{stage: 'a', outputs: ['x.nii.gz']}, {stage: 'b'}, {stage: 'c', outputs: ['y.nii.gz', 'z.nii.gz']}];
  expect(extractOutputFiles(events)).toEqual(['x.nii.gz', 'y.nii.gz', 'z.nii.gz']);
});

test('filterLogLines returns original text for empty query', () => {
  expect(filterLogLines('hello\nworld', '')).toBe('hello\nworld');
  expect(filterLogLines('hello\nworld', '  ')).toBe('hello\nworld');
});

test('filterLogLines filters lines by query and sanitizes MRI_EVENTs', () => {
  expect(filterLogLines('hello\nMRI_EVENT {}\nworld\nhello again', 'hello')).toBe('hello\nhello again');
  expect(filterLogLines('hello\nworld', 'WORLD')).toBe('world');
});

test('progressStepEvents keeps only events with a step descriptor', () => {
  const events = [{stage: 'a'}, {kind: 'event'}, {foo: 'bar'}];
  expect(progressStepEvents(events).length).toBe(2);
});

test('stepEventState extracts a normalized event state', () => {
  expect(stepEventState({state: 'RUNNING'})).toBe('running');
  expect(stepEventState({status: 'Done'})).toBe('done');
  expect(stepEventState({kind: 'Launch'})).toBe('launch');
  expect(stepEventState({})).toBe('unknown');
});

test('dotClassForState matches status colors', () => {
  expect(dotClassForState('running')).toMatch(/animate-pulse/);
  expect(dotClassForState('completed')).toMatch(/bg-cursor-semantic-success/);
  expect(dotClassForState('failed')).toMatch(/bg-cursor-semantic-error/);
  expect(dotClassForState('weird')).toMatch(/bg-cursor-muted/);
});

test('sidebarDotClass colors by job state', () => {
  expect(sidebarDotClass({state: 'running'})).toMatch(/animate-pulse/);
  expect(sidebarDotClass({state: 'completed'})).toMatch(/bg-cursor-semantic-success/);
  expect(sidebarDotClass({state: 'failed'})).toMatch(/bg-cursor-semantic-error/);
});

test('displayJobState returns formatted state labels', () => {
  expect(displayJobState('running')).toBe('Running');
  expect(displayJobState('completed')).toBe('Success');
  expect(displayJobState('failed')).toBe('Failed');
  expect(displayJobState('stopped')).toBe('Stopped');
});

test('deriveBatchImages combines job initial files with events', () => {
  const job = {
    input_files: ['/data/ADNI_011/001.mgz', '/data/ADNI_012/001.mgz'],
  };
  const events = [
    {kind: 'image_start', input_file: '/data/ADNI_011/001.mgz', idx: 1, total: 2},
    {kind: 'image_done', input_file: '/data/ADNI_011/001.mgz', subject_id: 'ADNI_011', success: true, duration_sec: 12.5, idx: 1, total: 2},
    {kind: 'image_start', input_file: '/data/ADNI_012/001.mgz', idx: 2, total: 2},
  ];

  const images = deriveBatchImages(events, job);
  expect(images).toHaveLength(2);
  expect(images[0]).toEqual({
    input_file: '/data/ADNI_011/001.mgz',
    subject_id: 'ADNI_011',
    idx: 1,
    total: 2,
    status: 'success',
    duration_sec: 12.5,
  });
  expect(images[1].status).toBe('running');
});

test('deriveBatchImages matches lazy upload local files with remote event paths without jumping count', () => {
  const job = {
    input_files: ['/home/trandangduat/mri-pipeline/data/001.nii.gz', '/home/trandangduat/mri-pipeline/data/002.nii.gz'],
  };
  const events = [
    {kind: 'image_start', input_file: '/home/catcd1/duat-jobs/001.nii.gz', idx: 1, total: 2},
    {kind: 'image_done', input_file: '/home/catcd1/duat-jobs/001.nii.gz', subject_id: '001', success: true, duration_sec: 4.2, idx: 1, total: 2},
    {kind: 'image_start', input_file: '/home/catcd1/duat-jobs/002.nii.gz', idx: 2, total: 2},
  ];

  const images = deriveBatchImages(events, job);
  expect(images).toHaveLength(2);
  expect(images[0].status).toBe('success');
  expect(images[0].duration_sec).toBe(4.2);
  expect(images[1].status).toBe('running');
});

test('deriveBatchSummary computes correct counts and percentage', () => {
  const images = [
    {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 3, status: 'success' as const},
    {input_file: 'b.nii', subject_id: 'b', idx: 2, total: 3, status: 'failed' as const},
    {input_file: 'c.nii', subject_id: 'c', idx: 3, total: 3, status: 'pending' as const},
  ];
  const summary = deriveBatchSummary(images);
  expect(summary.total).toBe(3);
  expect(summary.success).toBe(1);
  expect(summary.failed).toBe(1);
  expect(summary.pending).toBe(1);
  expect(summary.completedPercent).toBe(67);
});

test('deriveImageSteps distinguishes pending vs not_scheduled stages', () => {
  const stageOrder = ['preproc', 'recon', 'stats'];
  const selectedTools = {preproc: 'fsl'};
  const events = [
    {kind: 'image_start', input_file: 'a.nii'},
    {kind: 'progress', stage: 'preproc', status: 'running'},
    {kind: 'metrics', stage: 'preproc', cpu_pct: 45, ram_bytes: 1073741824, container_name: 'fsl-container'},
    {kind: 'progress', stage: 'preproc', status: 'ok'},
  ];
  const image = {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'running' as const};

  const steps = deriveImageSteps(events, image, selectedTools, stageOrder, {preproc: 'Preprocessing', recon: 'Reconstruction'});
  expect(steps).toHaveLength(3);
  expect(steps[0].status).toBe('success');
  expect(steps[0].container_name).toBe('fsl-container');
  expect(steps[1].status).toBe('not_scheduled');
  expect(steps[2].status).toBe('not_scheduled');
});

test('deriveImageSteps keeps scheduled stages pending until events run them', () => {
  const steps = deriveImageSteps([], {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'running'}, {preproc: 'cat_preproc', seg: 'cat_seg'}, ['preproc', 'seg'], {});
  expect(steps[0].status).toBe('pending');
  expect(steps[0].tool).toBe('cat_preproc');
  expect(steps[1].status).toBe('pending');
  expect(steps[1].tool).toBe('cat_seg');
});

test('deriveImageSteps does not promote no-tool stages from placeholder events', () => {
  const stageOrder = ['stage1', 'stage2', 'stage3'];
  const selectedTools = {stage1: 'tool1', stage3: 'tool3'};
  const image = {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'failed' as const};
  const events = [
    {kind: 'image_start', input_file: 'a.nii'},
    {kind: 'progress', stage: 'stage2', status: 'ok'},
    {kind: 'image_done', input_file: 'a.nii', success: false, log_text: '[stage2]  - OK'},
  ];
  const steps = deriveImageSteps(events, image, selectedTools, stageOrder, {});
  expect(steps[1].status).toBe('not_scheduled');
  expect(steps[1].tool).toBe('');
});

test('deriveImageSteps accepts event tool for stages missing selected tool metadata', () => {
  const image = {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'running' as const};
  const events = [{kind: 'image_start', input_file: 'a.nii'}, {kind: 'progress', stage: 'seg', status: 'running', tool: 'cat_seg'}];
  const steps = deriveImageSteps(events, image, {}, ['seg'], {});
  expect(steps[0].status).toBe('running');
  expect(steps[0].tool).toBe('cat_seg');
});

test('deriveJobDisplayMetadata reconciles status from terminal events and batch items', () => {
  const runningJob = {state: 'running', input_files: ['a.nii', 'b.nii']};
  const terminalEvents = [
    {kind: 'image_start', input_file: 'a.nii'},
    {kind: 'image_done', input_file: 'a.nii', success: true},
    {kind: 'image_start', input_file: 'b.nii'},
    {kind: 'image_done', input_file: 'b.nii', success: true},
    {kind: 'pipeline_completed'},
  ];
  const meta = deriveJobDisplayMetadata(runningJob, terminalEvents);
  expect(meta.status_reconciled).toBe('completed');

  const failedEvents = [
    {kind: 'image_start', input_file: 'a.nii'},
    {kind: 'image_done', input_file: 'a.nii', success: false},
    {kind: 'pipeline_failed'},
  ];
  const failedMeta = deriveJobDisplayMetadata(runningJob, failedEvents);
  expect(failedMeta.status_reconciled).toBe('failed');
});

test('deriveImageSteps keeps unexecuted stages as pending when subject only partially completed', () => {
  const stageOrder = ['reorientation', 'brain_extraction', 'segmentation'];
  const selectedTools = {
    reorientation: 'fs_reorient',
    brain_extraction: 'fs_bet',
    segmentation: 'synthseg',
  };
  const image = {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'failed' as const};
  const events = [
    {kind: 'image_start', input_file: 'a.nii'},
    {kind: 'progress', stage: 'reorientation', status: 'ok', elapsed_sec: 10},
    {kind: 'progress', stage: 'brain_extraction', status: 'ok', elapsed_sec: 75},
    {
      kind: 'image_done',
      input_file: 'a.nii',
      success: false,
      log_text: '[reorientation] fs_reorient - OK (10.0s)\n[brain_extraction] fs_bet - OK (75.0s)',
    },
  ];
  const steps = deriveImageSteps(events, image, selectedTools, stageOrder, {});
  expect(steps[0].status).toBe('success');
  expect(steps[1].status).toBe('success');
  expect(steps[2].status).toBe('pending');
});

test('deriveBatchImages reconciles running/pending images to stopped when job is stopped', () => {
  const job = {state: 'stopped'};
  const events = [
    {kind: 'image_start', input_file: 'a.nii', idx: 1, total: 2},
    {kind: 'image_start', input_file: 'b.nii', idx: 2, total: 2},
  ];
  const images = deriveBatchImages(events, job);
  expect(images.length).toBe(2);
  expect(images[0].status).toBe('stopped');
  expect(images[1].status).toBe('stopped');
});

test('deriveBatchImages marks subject as failed if image_done event has success=true but log_text only ran partial stages', () => {
  const job = {
    state: 'failed',
    run_request_summary: {
      selected_tools: {
        reorientation: 'tool1',
        brain_extraction: 'tool2',
        segmentation: 'tool3',
      },
    },
  };
  const events = [
    {kind: 'image_start', input_file: 'a.nii', idx: 1, total: 1},
    {
      kind: 'image_done',
      input_file: 'a.nii',
      success: true,
      log_text: '[reorientation] tool1 - OK (9.7s)\n[brain_extraction] tool2 - OK (76.9s)',
    },
  ];
  const images = deriveBatchImages(events, job);
  expect(images.length).toBe(1);
  expect(images[0].status).toBe('failed');
});

test('deriveImageSteps sets running and pending scheduled stages to stopped when image status is stopped', () => {
  const stageOrder = ['reorientation', 'brain_extraction', 'segmentation', 'stat_calculation'];
  const selectedTools = {
    reorientation: 'fs_reorient',
    segmentation: 'synthseg',
    stat_calculation: 'fs_stats',
  };
  const image = {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'stopped' as const};
  const events = [
    {kind: 'image_start', input_file: 'a.nii'},
    {kind: 'progress', stage: 'reorientation', status: 'ok', elapsed_sec: 10},
    {kind: 'progress', stage: 'segmentation', status: 'stopped', elapsed_sec: 45},
  ];
  const steps = deriveImageSteps(events, image, selectedTools, stageOrder, {});
  expect(steps[0].status).toBe('success');
  expect(steps[1].status).toBe('not_scheduled');
  expect(steps[2].status).toBe('stopped');
  expect(steps[3].status).toBe('stopped');
});

test('deriveImageSteps parses SUCCESS and STOPPED in image_done log text', () => {
  const stageOrder = ['stage1', 'stage2', 'stage3'];
  const selectedTools = {stage1: 'tool1', stage2: 'tool2', stage3: 'tool3'};
  const image = {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'stopped' as const};
  const events = [
    {kind: 'image_start', input_file: 'a.nii'},
    {
      kind: 'image_done',
      input_file: 'a.nii',
      success: false,
      status: 'stopped',
      log_text: '[stage1] tool1 - SUCCESS (10.0s)\n[stage2] tool2 - STOPPED (5.0s)',
    },
  ];
  const steps = deriveImageSteps(events, image, selectedTools, stageOrder, {});
  expect(steps[0].status).toBe('success');
  expect(steps[1].status).toBe('stopped');
  expect(steps[2].status).toBe('stopped');
});

test('isEventForImage matches truncated container names for long subject IDs', () => {
  const image = {
    input_file: '/home/catcd1/neuroflow-benchmark/test-lazy-upload/ADNI_007_S_0249_MR_MPR__GradWarp__B1_Correction__N3__Scaled_2_Br_20081001120039197_S11911_I118687__001/001.mgz',
    subject_id: 'ADNI_007_S_0249_MR_MPR__GradWarp__B1_Correction__N3__Scaled_2_Br_20081001120039197_S11911_I118687__001',
    idx: 1,
    total: 3,
    status: 'running' as const,
  };

  const truncatedEvent = {
    kind: 'metrics',
    container_name: 'mri-ADNI_007_S_0249_MR_MPR__GradWarp__B1_Correction__N3__Scaled_2_Br_20081001120-2ba288d9',
    cpu_pct: 100.5,
    ram_bytes: 50000000,
  };

  expect(isEventForImage(truncatedEvent, image)).toBe(true);

  const nonMatchingEvent = {
    kind: 'metrics',
    container_name: 'mri-ADNI_011_S_0241_MR_MPR__GradWarp__B1_Correction__N3__Scaled_Br_200905111120-1d8cf01b',
    cpu_pct: 100.5,
    ram_bytes: 50000000,
  };

  expect(isEventForImage(nonMatchingEvent, image)).toBe(false);
});

test('isEventForImage matches explicit subject_id and input_file in event', () => {
  const image = {
    input_file: '/data/sub-01/001.mgz',
    subject_id: 'sub-01',
    idx: 1,
    total: 1,
    status: 'running' as const,
  };

  expect(isEventForImage({kind: 'metrics', subject_id: 'sub-01'}, image)).toBe(true);
  expect(isEventForImage({kind: 'metrics', input_file: '/data/sub-01/001.mgz'}, image)).toBe(true);
  expect(isEventForImage({kind: 'metrics', subject_id: 'sub-02'}, image)).toBe(false);
});

test('deriveMetricsSeries extracts CPU and RAM points for long subject IDs with truncated container names', () => {
  const image = {
    input_file: '/data/ADNI_007_S_0249_MR_MPR__GradWarp__B1_Correction__N3__Scaled_2_Br_20081001120039197_S11911_I118687__001/001.mgz',
    subject_id: 'ADNI_007_S_0249_MR_MPR__GradWarp__B1_Correction__N3__Scaled_2_Br_20081001120039197_S11911_I118687__001',
    idx: 1,
    total: 1,
    status: 'running' as const,
  };

  const events = [
    {kind: 'image_start', input_file: image.input_file},
    {
      kind: 'metrics',
      stage: 'reorientation',
      tool: 'fs8_reorient',
      container_name: 'mri-ADNI_007_S_0249_MR_MPR__GradWarp__B1_Correction__N3__Scaled_2_Br_20081001120-2ba288d9',
      cpu_pct: 100.27,
      ram_bytes: 104857600, // 100 MB
    },
    {
      kind: 'metrics',
      stage: 'reorientation',
      tool: 'fs8_reorient',
      container_name: 'mri-ADNI_007_S_0249_MR_MPR__GradWarp__B1_Correction__N3__Scaled_2_Br_20081001120-2ba288d9',
      cpu_pct: 101.4,
      ram_bytes: 209715200, // 200 MB
    },
  ];

  const series = deriveMetricsSeries(events, image);
  expect(series.cpuSeries).toEqual([100.27, 101.4]);
  expect(series.ramSeries).toEqual([100, 200]);
  expect(series.latestContainer).toBe('mri-ADNI_007_S_0249_MR_MPR__GradWarp__B1_Correction__N3__Scaled_2_Br_20081001120-2ba288d9');
});

test('deriveSubjectStageInfo shows currently running step when a step is active', () => {
  const image = {input_file: 'a.nii', subject_id: 'sub-01', idx: 1, total: 2, status: 'running' as const};
  const steps = [
    {stage: 'reorient', label: 'Reorientation', tool: 'fs_reorient', status: 'success' as const},
    {stage: 'segmentation', label: 'Segmentation', tool: 'synthseg', status: 'running' as const},
    {stage: 'stats', label: 'Stats', tool: 'fs_stats', status: 'pending' as const},
  ];
  const info = deriveSubjectStageInfo(image, steps);
  expect(info.label).toBe('Segmentation');
  expect(info.status).toBe('running');
});

test('deriveSubjectStageInfo shows next pending step when subject is running between stages', () => {
  const image = {input_file: 'a.nii', subject_id: 'sub-02', idx: 2, total: 3, status: 'running' as const};
  const steps = [
    {stage: 'reorientation', label: 'Reorientation, resize', tool: 'fs8_reorient', status: 'success' as const},
    {stage: 'brain_extraction', label: 'Brain Extraction', tool: '', status: 'not_scheduled' as const},
    {stage: 'segmentation', label: 'Subcortical Segmentation', tool: 'synthseg', status: 'pending' as const},
    {stage: 'stats_extraction', label: 'Statistics & Atlas Mapping', tool: 'fs8_stats', status: 'pending' as const},
  ];
  const info = deriveSubjectStageInfo(image, steps);
  expect(info.label).toBe('Subcortical Segmentation');
  expect(info.status).toBe('pending');
});

test('deriveSubjectStageInfo shows success step when subject status is success', () => {
  const image = {input_file: 'a.nii', subject_id: 'sub-01', idx: 1, total: 1, status: 'success' as const};
  const steps = [
    {stage: 'reorient', label: 'Reorientation', tool: 'fs_reorient', status: 'success' as const},
    {stage: 'stats', label: 'Stats', tool: 'fs_stats', status: 'success' as const},
  ];
  const info = deriveSubjectStageInfo(image, steps);
  expect(info.label).toBe('Stats');
  expect(info.status).toBe('success');
});

test('deriveSubjectStageInfo shows first step as queued when subject status is pending', () => {
  const image = {input_file: 'a.nii', subject_id: 'sub-03', idx: 3, total: 3, status: 'pending' as const};
  const steps = [
    {stage: 'reorientation', label: 'Reorientation, resize', tool: 'fs8_reorient', status: 'pending' as const},
    {stage: 'segmentation', label: 'Subcortical Segmentation', tool: 'synthseg', status: 'pending' as const},
  ];
  const info = deriveSubjectStageInfo(image, steps);
  expect(info.label).toBe('Reorientation, resize');
  expect(info.status).toBe('pending');
});





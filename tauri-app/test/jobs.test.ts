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
  deriveSubjectLabel,
  sanitizeTerminalLog,
  deriveJobDisplayMetadata,
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

test('deriveBatchImages reconciles running/pending images to interrupted when job is stopped', () => {
  const job = {state: 'stopped'};
  const events = [
    {kind: 'image_start', input_file: 'a.nii', idx: 1, total: 2},
    {kind: 'image_start', input_file: 'b.nii', idx: 2, total: 2},
  ];
  const images = deriveBatchImages(events, job);
  expect(images.length).toBe(2);
  expect(images[0].status).toBe('interrupted');
  expect(images[1].status).toBe('interrupted');
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



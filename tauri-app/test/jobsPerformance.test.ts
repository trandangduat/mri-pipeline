import {describe, expect, it} from 'vitest';
import {
  deriveBatchImages,
  deriveImageSteps,
  deriveJobDisplayMetadata,
  deriveSubjectStageInfo,
  reduceBatchImages,
} from '../src/lib/jobs';
import type {BatchImageItem} from '../src/lib/jobs';
import {capLogLines} from '../src/stores/jobsStore';
import type {PipelineEvent} from '../src/types/backend';

describe('capLogLines ring buffer', () => {
  it('preserves logs under the line limit', () => {
    const text = 'line 1\nline 2\nline 3';
    expect(capLogLines(text, 5)).toBe(text);
  });

  it('truncates older lines when exceeding maxLines', () => {
    const lines = Array.from({length: 10}, (_, i) => `line ${i + 1}`).join('\n');
    const capped = capLogLines(lines, 3);
    expect(capped).toBe('line 8\nline 9\nline 10');
  });

  it('handles empty input gracefully', () => {
    expect(capLogLines('', 100)).toBe('');
  });
});

describe('reduceBatchImages incremental reducer', () => {
  const job = {
    job_id: 'job_test',
    state: 'running',
    input_files: ['/data/sub-01.nii.gz', '/data/sub-02.nii.gz'],
  };

  it('initializes from scratch when currentImages is empty', () => {
    const initialEvents: PipelineEvent[] = [
      {kind: 'image_start', input_file: '/data/sub-01.nii.gz', idx: 1, total: 2},
    ];
    const images = reduceBatchImages([], initialEvents, job);
    expect(images).toHaveLength(2);
    expect(images.find((img) => img.input_file === '/data/sub-01.nii.gz')?.status).toBe('running');
    expect(images.find((img) => img.input_file === '/data/sub-02.nii.gz')?.status).toBe('pending');
  });

  it('applies delta events incrementally to existing images', () => {
    const initialEvents: PipelineEvent[] = [
      {kind: 'image_start', input_file: '/data/sub-01.nii.gz', idx: 1, total: 2},
    ];
    const step1 = reduceBatchImages([], initialEvents, job);

    // Delta: sub-01 finishes, sub-02 starts
    const deltaEvents: PipelineEvent[] = [
      {kind: 'image_done', input_file: '/data/sub-01.nii.gz', success: true, idx: 1, total: 2, duration_sec: 12.5},
      {kind: 'image_start', input_file: '/data/sub-02.nii.gz', idx: 2, total: 2},
    ];
    const step2 = reduceBatchImages(step1, deltaEvents, job);

    expect(step2).toHaveLength(2);
    const img1 = step2.find((img) => img.input_file === '/data/sub-01.nii.gz');
    const img2 = step2.find((img) => img.input_file === '/data/sub-02.nii.gz');
    expect(img1?.status).toBe('success');
    expect(img1?.duration_sec).toBe(12.5);
    expect(img2?.status).toBe('running');
  });

  it('deriveJobDisplayMetadata accepts precomputed batch images without re-evaluating deriveBatchImages', () => {
    const precomputed = deriveBatchImages([], job);
    const meta = deriveJobDisplayMetadata(job, [], precomputed);
    expect(meta.status_reconciled).toBe('running');
  });

  it('deriveJobDisplayMetadata preserves failed status and never reverts to running despite running image', () => {
    const crashedJob = {...job, state: 'failed'};
    const runningImages = [
      {input_file: '/data/sub-01.nii.gz', subject_id: 'sub-01', idx: 1, total: 2, status: 'running' as const},
      {input_file: '/data/sub-02.nii.gz', subject_id: 'sub-02', idx: 2, total: 2, status: 'pending' as const},
    ];
    const meta = deriveJobDisplayMetadata(crashedJob, [], runningImages);
    expect(meta.status_reconciled).toBe('failed');
  });

  it('reduceBatchImages reconciles lingering running/pending subjects to failed when job fails', () => {
    const crashedJob = {...job, state: 'failed'};
    const runningImages = [
      {input_file: '/data/sub-01.nii.gz', subject_id: 'sub-01', idx: 1, total: 2, status: 'running' as const},
      {input_file: '/data/sub-02.nii.gz', subject_id: 'sub-02', idx: 2, total: 2, status: 'pending' as const},
    ];
    const reconciled = reduceBatchImages(runningImages, [], crashedJob);
    expect(reconciled.every((img) => img.status === 'failed')).toBe(true);
  });

  it('deriveImageSteps transitions active running stage to failed on failed subject', () => {
    const stageOrder = ['dicom_conversion', 'template_registration', 'statistics'];
    const stageLabels = {
      dicom_conversion: 'DICOM Conversion',
      template_registration: 'Template Registration',
      statistics: 'Statistics',
    };
    const selectedTools = {
      dicom_conversion: 'dcm2niix',
      template_registration: 'fs8_template_registration',
      statistics: 'cat12_stats',
    };
    const events: PipelineEvent[] = [
      {kind: 'image_start', input_file: '/data/sub-01.nii.gz'},
      {kind: 'progress', input_file: '/data/sub-01.nii.gz', stage: 'dicom_conversion', status: 'success'},
      {kind: 'progress', input_file: '/data/sub-01.nii.gz', stage: 'template_registration', status: 'running'},
    ];
    const failedImage: BatchImageItem = {
      input_file: '/data/sub-01.nii.gz',
      subject_id: 'sub-01',
      idx: 1,
      total: 1,
      status: 'failed',
    };

    const steps = deriveImageSteps(events, failedImage, selectedTools, stageOrder, stageLabels);
    const step1 = steps.find((s) => s.stage === 'dicom_conversion');
    const step2 = steps.find((s) => s.stage === 'template_registration');
    const step3 = steps.find((s) => s.stage === 'statistics');

    expect(step1?.status).toBe('success');
    expect(step2?.status).toBe('failed');
    expect(step3?.status).toBe('pending');

    const stageInfo = deriveSubjectStageInfo(failedImage, steps);
    expect(stageInfo.label).toBe('Template Registration');
    expect(stageInfo.status).toBe('failed');
  });

  it('deriveImageSteps falls back to regex matching done in Xs from message', () => {
    const stageOrder = ['reorientation'];
    const stageLabels = {reorientation: 'Reorientation'};
    const selectedTools = {reorientation: 'fs_reorient'};
    const events: PipelineEvent[] = [
      {kind: 'image_start', input_file: '/data/sub-01.nii.gz'},
      {
        kind: 'progress',
        input_file: '/data/sub-01.nii.gz',
        stage: 'reorientation',
        status: 'success',
        msg: 'Reorientation, resize done in 10s',
      },
    ];
    const img: BatchImageItem = {
      input_file: '/data/sub-01.nii.gz',
      subject_id: 'sub-01',
      idx: 1,
      total: 1,
      status: 'running',
    };
    const steps = deriveImageSteps(events, img, selectedTools, stageOrder, stageLabels);
    expect(steps[0].elapsed_sec).toBe(10);
  });
});

import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect, test} from 'vitest';
import {DownloadOutputsDialog} from '../src/components/DownloadOutputsDialog';

const baseProps = {
  open: true,
  jobId: 'remote_job_123',
  localDir: '',
  phase: 'select' as const,
  steps: [],
  onBrowse: () => {},
  onStart: () => {},
  onResume: () => {},
  onClose: () => {},
};

function runningProps(overrides: Record<string, unknown> = {}) {
  return {
    ...baseProps,
    phase: 'running' as const,
    steps: [
      {id: 'connect', label: 'Connecting to server', status: 'done' as const},
      {id: 'count', label: 'Counting remote files', status: 'done' as const},
      {
        id: 'copy',
        label: 'Copying outputs',
        status: 'running' as const,
        detail: 'Downloading file: warp.to.mni152.1.0mm.inv.nii.gz → C:/Users/A/outputs/warp.to.mni152.1.0mm.inv.nii.gz',
      },
    ],
    copiedFiles: 3,
    totalFiles: 5,
    ...overrides,
  };
}

test('select phase renders destination input and Start button disabled without path', () => {
  render(<DownloadOutputsDialog {...baseProps} />);
  expect(screen.getByText('Download Server Outputs')).toBeTruthy();
  expect(screen.getByText('Destination')).toBeTruthy();
  const input = screen.getByPlaceholderText('Choose a folder…');
  expect(input).toBeTruthy();
  expect(input).toHaveAttribute('readonly');
  expect(screen.getByText('Start Download')).toBeDisabled();
});

test('select phase enables Start button when localDir is set and shows the full path in one box', () => {
  render(<DownloadOutputsDialog {...baseProps} localDir="C:\base" />);
  expect(screen.getByText('Start Download')).not.toBeDisabled();
  expect(screen.getByDisplayValue('C:\\base\\remote_job_123')).toBeTruthy();
});

test('select phase shows no status badge', () => {
  render(<DownloadOutputsDialog {...baseProps} localDir="C:\base" />);
  expect(screen.queryByText('Ready')).toBeNull();
  expect(screen.queryByText('Downloading')).toBeNull();
  expect(screen.queryByText('Done')).toBeNull();
});

test('running phase renders hero percent, counts, speed and ETA', () => {
  render(<DownloadOutputsDialog {...runningProps({speedFilesPerSec: 2.5, etaSeconds: 65})} />);
  expect(screen.getByText('Downloading Outputs')).toBeTruthy();
  expect(screen.queryByText('Downloading')).toBeNull();
  expect(screen.getByText('60%')).toBeTruthy();
  expect(screen.getByText('3 of 5 files')).toBeTruthy();
  expect(screen.getByText('2.5 files/s')).toBeTruthy();
  expect(screen.getByText('ETA 1m 05s')).toBeTruthy();
  expect(screen.queryByText('Copying outputs…')).toBeNull();
  expect(screen.getByText('warp.to.mni152.1.0mm.inv.nii.gz')).toBeTruthy();
  expect(screen.getByText('C:/Users/A/outputs/warp.to.mni152.1.0mm.inv.nii.gz')).toBeTruthy();
});

test('running phase hides speed and ETA without enough samples', () => {
  render(<DownloadOutputsDialog {...runningProps()} />);
  expect(screen.queryByText(/files\/s/)).toBeNull();
  expect(screen.queryByText(/ETA/)).toBeNull();
});

test('running phase uses text-sm or larger, never text-2xs', () => {
  const {container} = render(<DownloadOutputsDialog {...runningProps({speedFilesPerSec: 1})} />);
  expect(container.querySelector('.text-2xs')).toBeNull();
});

test('success phase renders file count and Copy Path', async () => {
  const onClose = () => {};
  let clipboard = '';
  Object.defineProperty(navigator, 'clipboard', {
    value: {writeText: (t: string) => { clipboard = t; return Promise.resolve(); }},
    configurable: true,
  });
  render(
    <DownloadOutputsDialog
      {...baseProps}
      phase="success"
      copiedFiles={5}
      totalFiles={5}
      finalPath="/tmp/outputs/remote_job_123"
      onClose={onClose}
    />,
  );
  expect(screen.getByText('Download Complete')).toBeTruthy();
  expect(screen.getByText('Downloaded 5 files')).toBeTruthy();
  expect(screen.getByText('/tmp/outputs/remote_job_123')).toBeTruthy();
  await userEvent.click(screen.getByText('Copy Path'));
  expect(clipboard).toBe('/tmp/outputs/remote_job_123');
  expect(screen.getByText('Copied')).toBeTruthy();
});

test('failed phase renders error message and Retry', () => {
  let resumed = 0;
  render(
    <DownloadOutputsDialog
      {...baseProps}
      phase="failed"
      errorMessage="SSH connection failed"
      onResume={() => { resumed += 1; }}
    />,
  );
  expect(screen.getByText('Download Failed')).toBeTruthy();
  expect(screen.getByText('SSH connection failed')).toBeTruthy();
  return userEvent.click(screen.getByText('Retry')).then(() => {
    expect(resumed).toBe(1);
  });
});

test('cancelled failure renders Stopped state with Resume Download', async () => {
  let resumed = 0;
  render(
    <DownloadOutputsDialog
      {...baseProps}
      phase="failed"
      cancelled
      errorMessage="Download stopped. Resume to continue where it stopped."
      onResume={() => { resumed += 1; }}
    />,
  );
  expect(screen.getByText('Download Stopped')).toBeTruthy();
  await userEvent.click(screen.getByText('Resume Download'));
  expect(resumed).toBe(1);
});

test('calls onStart when Start Download is clicked', async () => {
  let started = 0;
  render(<DownloadOutputsDialog {...baseProps} localDir="/tmp/outputs" onStart={() => { started += 1; }} />);
  await userEvent.click(screen.getByText('Start Download'));
  expect(started).toBe(1);
});

test('calls onClose when Cancel is clicked', async () => {
  let closed = 0;
  render(<DownloadOutputsDialog {...baseProps} onClose={() => { closed += 1; }} />);
  await userEvent.click(screen.getByText('Cancel'));
  expect(closed).toBe(1);
});

test('running phase with onStop renders Stop Download and calls it', async () => {
  let stopped = 0;
  let closed = 0;
  render(
    <DownloadOutputsDialog
      {...runningProps({onClose: () => { closed += 1; }, onStop: () => { stopped += 1; }, canClose: false})}
    />,
  );
  await userEvent.click(screen.getByText('Stop Download'));
  expect(stopped).toBe(1);
  expect(closed).toBe(0);
});

test('running phase without onStop renders no Stop button', () => {
  render(<DownloadOutputsDialog {...runningProps()} />);
  expect(screen.queryByText('Stop Download')).toBeNull();
});

test('does not render when open is false', () => {
  render(<DownloadOutputsDialog {...baseProps} open={false} />);
  expect(screen.queryByText('Download Server Outputs')).toBeNull();
});

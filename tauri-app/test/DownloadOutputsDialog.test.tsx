import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect, test, vi} from 'vitest';
import {DownloadOutputsDialog} from '../src/components/DownloadOutputsDialog';

const baseProps = {
  open: true,
  jobId: 'remote_job_123',
  remotePath: '/workspace/job_123/outputs',
  localDir: '',
  onLocalDirChange: vi.fn(),
  phase: 'select' as const,
  steps: [],
  logs: [],
  onBrowse: vi.fn(),
  onStart: vi.fn(),
  onClose: vi.fn(),
};

test('select phase renders destination input and Start button disabled without path', () => {
  render(<DownloadOutputsDialog {...baseProps} />);
  expect(screen.getByText('Download Server Outputs')).toBeTruthy();
  expect(screen.getByText('Save outputs to')).toBeTruthy();
  expect(screen.getByPlaceholderText('Select or type a local folder...')).toBeTruthy();
  expect(screen.getByText('Start Download')).toBeDisabled();
});

test('select phase enables Start button when localDir is set', () => {
  render(<DownloadOutputsDialog {...baseProps} localDir="/tmp/outputs" />);
  expect(screen.getByText('Start Download')).not.toBeDisabled();
});

test('running phase renders progress counts and disables close/start', () => {
  render(
    <DownloadOutputsDialog
      {...baseProps}
      phase="running"
      steps={[
        {id: 'connect', label: 'Connecting to server', status: 'done'},
        {id: 'count', label: 'Counting remote files', status: 'done', detail: 'Found 5 file(s)'},
        {id: 'copy', label: 'Copying outputs', status: 'running'},
      ]}
      copiedFiles={3}
      totalFiles={5}
    />,
  );
  expect(screen.getByText('Downloading Outputs...')).toBeTruthy();
  expect(screen.getByText('3 of 5 files')).toBeTruthy();
  expect(screen.getByText('60%')).toBeTruthy();
  expect(screen.getByText('Connecting to server')).toBeTruthy();
});

test('success phase renders final path and file count', () => {
  render(
    <DownloadOutputsDialog
      {...baseProps}
      phase="success"
      copiedFiles={5}
      totalFiles={5}
      finalPath="/tmp/outputs/remote_job_123"
    />,
  );
  expect(screen.getByText('Download Complete')).toBeTruthy();
  expect(screen.getByText('Downloaded 5 files successfully')).toBeTruthy();
  expect(screen.getByText('/tmp/outputs/remote_job_123')).toBeTruthy();
  expect(screen.getByText('Close')).toBeTruthy();
});

test('failed phase renders error message', () => {
  render(
    <DownloadOutputsDialog
      {...baseProps}
      phase="failed"
      errorMessage="SSH connection failed"
    />,
  );
  expect(screen.getByText('Download Failed')).toBeTruthy();
  expect(screen.getByText('Download failed')).toBeTruthy();
  expect(screen.getByText('SSH connection failed')).toBeTruthy();
  expect(screen.getByText('Close')).toBeTruthy();
});

test('calls onStart when Start Download is clicked', async () => {
  const onStart = vi.fn();
  render(<DownloadOutputsDialog {...baseProps} localDir="/tmp/outputs" onStart={onStart} />);
  await userEvent.click(screen.getByText('Start Download'));
  expect(onStart).toHaveBeenCalledOnce();
});

test('calls onClose when Cancel is clicked', async () => {
  const onClose = vi.fn();
  render(<DownloadOutputsDialog {...baseProps} onClose={onClose} />);
  await userEvent.click(screen.getByText('Cancel'));
  expect(onClose).toHaveBeenCalledOnce();
});

test('does not render when open is false', () => {
  render(<DownloadOutputsDialog {...baseProps} open={false} />);
  expect(screen.queryByText('Download Server Outputs')).toBeNull();
});

test('running phase renders logs with break-all and whitespace-pre-wrap classes', () => {
  const longPath = 'Copying /very/long/nested/directory/structure/that/could/overflow/the/container/if/not/wrapped/output.nii.gz';
  render(
    <DownloadOutputsDialog
      {...baseProps}
      phase="running"
      steps={[{id: 'copy', label: 'Copying outputs', status: 'running'}]}
      logs={[longPath]}
    />,
  );
  const logElement = screen.getByText(longPath);
  expect(logElement).toBeTruthy();
  expect(logElement.className).toContain('break-all');
  expect(logElement.className).toContain('whitespace-pre-wrap');
});

import React from 'react';
import {describe, it, expect, beforeEach} from 'vitest';
import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {JobsPage} from '../src/pages/JobsPage';
import {useJobsStore} from '../src/stores/jobsStore';
import {useRemoteStore} from '../src/stores/remoteStore';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {retry: false},
  },
});

function renderJobsPage(initialPath = '/jobs') {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:jobId" element={<JobsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('JobsPage Redesign', () => {
  beforeEach(() => {
    useJobsStore.setState({
      latestJobs: [
        {
          job_id: 'job_local_01',
          display_name: 'job_local_01',
          target: 'Local',
          state: 'running',
          started_at: 1700002000,
        },
        {
          job_id: 'job_local_02',
          display_name: 'job_local_02',
          target: 'Local',
          state: 'completed',
          started_at: 1700001000,
        },
        {
          job_id: 'job_server_01',
          display_name: 'job_server_01',
          target: 'Server',
          state: 'failed',
          started_at: 1700003000,
        },
      ],
      selectedJobId: null,
      jobEvents: [],
      outputText: '',
    });
  });

  it('renders Jobs Overview list with Local Jobs and Server Jobs sections when no job is selected', () => {
    renderJobsPage('/jobs');

    expect(screen.getByText(/Local Jobs \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/Server Jobs \(1\)/)).toBeInTheDocument();

    // Check job cards exist
    expect(screen.getByText('job_local_01')).toBeInTheDocument();
    expect(screen.getByText('job_local_02')).toBeInTheDocument();
    expect(screen.getByText('job_server_01')).toBeInTheDocument();
  });

  it('navigates to job detail view when a job card is clicked', () => {
    renderJobsPage('/jobs');

    const jobCard = screen.getByText('job_local_01');
    fireEvent.click(jobCard);

    // Should now show Back button in detail view
    expect(screen.getByText('Back to Jobs')).toBeDefined();
  });

  it('returns to jobs list when Back button is clicked', () => {
    renderJobsPage('/jobs/job_local_01');

    expect(screen.getByText('Back to Jobs')).toBeDefined();

    const backButton = screen.getByRole('button', {name: /back to jobs/i});
    fireEvent.click(backButton);

    // Should return to the overview list
    expect(screen.getByText(/Local Jobs \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/Server Jobs \(1\)/)).toBeInTheDocument();
  });

  it('renders Server Jobs section first when runtimeTarget is Server', async () => {
    const {usePipelineFormStore} = await import('../src/stores/pipelineFormStore');
    usePipelineFormStore.setState({
      formValues: {
        ...usePipelineFormStore.getState().formValues,
        runtimeTarget: 'Server',
      },
    });

    renderJobsPage('/jobs');

    const headings = screen.getAllByRole('heading', {level: 2});
    expect(headings[0].textContent).toContain('Server Jobs (1)');
    expect(headings[1].textContent).toContain('Local Jobs (2)');

    // Reset back to Local
    usePipelineFormStore.setState({
      formValues: {
        ...usePipelineFormStore.getState().formValues,
        runtimeTarget: 'Local',
      },
    });
  });

  it('renders clean h2 title and Preset row in metadata table for single job view', () => {
    useJobsStore.setState({
      selectedJobId: 'job_local_01',
      latestJobs: [
        {
          job_id: 'job_local_01',
          display_name: 'job_local_01',
          target: 'Local',
          state: 'running',
          pipeline_mode: 'FastSurfer',
          run_request_summary: {
            pipeline_mode: 'FastSurfer',
            threads: 4,
          },
        },
      ],
    });

    renderJobsPage('/jobs/job_local_01');

    // Clean h2 heading without select dropdown
    const heading = screen.getByRole('heading', {level: 2, name: /job_local_01/i});
    expect(heading).toBeDefined();
    expect(screen.queryByRole('combobox')).toBeNull();

    // Preset row in metadata table
    expect(screen.getByText('Preset')).toBeDefined();
    expect(screen.getByText('FastSurfer')).toBeDefined();
  });

  it('renders mixed batch summary slices and truncates long job names', async () => {
    const longName = 'job_20260822_191740_with_a_long_workspace_name';
    useJobsStore.setState({
      selectedJobId: null,
      latestJobs: [
        {
          job_id: 'job_mixed',
          display_name: longName,
          target: 'Server',
          state: 'failed',
          started_at: 1700003000,
          batch_summary: {total: 10, success: 3, failed: 7, running: 0, pending: 0},
        },
      ],
    });

    renderJobsPage('/jobs');

    await waitFor(() => {
      const title = screen.getByText(longName);
      expect(title.className).toContain('truncate');
      expect(title.closest('[role="button"]')?.querySelector('[title="Batch summary"] svg')?.querySelectorAll('path')).toHaveLength(2);
    });
  });

  it('opens Delete Job ConfirmDialog when delete button is clicked on a completed job', () => {
    renderJobsPage('/jobs');

    const deleteBtn = screen.getByRole('button', {name: /Delete job_local_02/i});
    fireEvent.click(deleteBtn);

    // Confirm dialog should open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Delete Job'})).toBeInTheDocument();
    expect(screen.getAllByText('job_local_02').length).toBeGreaterThanOrEqual(2);

    // Cancel closes dialog
    const cancelBtn = screen.getByRole('button', {name: 'Cancel'});
    fireEvent.click(cancelBtn);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens Stop Job ConfirmDialog when Stop Job button is clicked in detail view', () => {
    useJobsStore.setState({
      selectedJobId: 'job_local_01',
      latestJobs: [
        {
          job_id: 'job_local_01',
          display_name: 'job_local_01',
          target: 'Local',
          state: 'running',
          started_at: 1700002000,
        },
      ],
    });

    renderJobsPage('/jobs/job_local_01');

    const stopButton = screen.getByRole('button', {name: /stop job/i});
    fireEvent.click(stopButton);

    // Confirm dialog should open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Stop Job'})).toBeInTheDocument();
    expect(screen.getAllByText('job_local_01').length).toBeGreaterThanOrEqual(2);

    // Cancel closes dialog
    const cancelBtn = screen.getByRole('button', {name: 'Cancel'});
    fireEvent.click(cancelBtn);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders Loading... on initial load when no jobs have been loaded yet', () => {
    useJobsStore.setState({
      latestJobs: [],
      hasLoadedInitialJobs: false,
      selectedJobId: null,
    });

    renderJobsPage('/jobs');

    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.queryByText(/No local jobs found/)).toBeNull();
    expect(screen.queryByText(/No server jobs found/)).toBeNull();
  });

  it('renders empty headers with no placeholder text when loaded and jobs list is empty', async () => {
    useJobsStore.setState({
      latestJobs: [],
      hasLoadedInitialJobs: true,
      selectedJobId: null,
    });

    renderJobsPage('/jobs');

    await waitFor(() => {
      expect(screen.getByText(/Local Jobs \(0\)/)).toBeInTheDocument();
      expect(screen.getByText(/Server Jobs \(0\)/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/No local jobs found/)).toBeNull();
    expect(screen.queryByText(/No server jobs found/)).toBeNull();
  });

  it('renders Refresh button with text-sm font-medium typography matching Tools Configuration', async () => {
    useJobsStore.setState({
      latestJobs: [],
      hasLoadedInitialJobs: true,
      selectedJobId: null,
    });

    renderJobsPage('/jobs');

    await waitFor(() => {
      const refreshBtn = screen.getByRole('button', {name: /refresh/i});
      expect(refreshBtn.className).toContain('text-sm');
      expect(refreshBtn.className).toContain('font-medium');
    });
  });
});

describe('JobsPage connection state', () => {
  beforeEach(() => {
    useRemoteStore.getState().reset();
    useJobsStore.setState({
      latestJobs: [
        {
          job_id: 'job_local_01',
          display_name: 'job_local_01',
          target: 'Local',
          state: 'completed',
          started_at: 1700002000,
        },
        {
          job_id: 'job_server_01',
          display_name: 'job_server_01',
          target: 'Server',
          state: 'completed',
          started_at: 1700003000,
        },
      ],
      hasLoadedInitialJobs: true,
      selectedJobId: null,
      jobEvents: [],
      outputText: '',
    });
  });

  it('never renders the removed Lagging badge', () => {
    useRemoteStore.setState({connected: true});
    renderJobsPage('/jobs');

    expect(screen.queryByText('Lagging')).toBeNull();
  });

  it('shows no inline banner (warning lives in the global footer line) but marks stale and blocks server delete when SSH is down', () => {
    useRemoteStore.setState({
      connected: true,
      sshStatus: 'disconnected',
      sshFailures: 1,
      sshLastError: 'SSH connection failed: timeout',
      sshLastSeenAt: Date.now() - 60_000,
    });
    renderJobsPage('/jobs');

    // Big inline banners are gone; only the compact Stale chip remains.
    expect(screen.queryByText(/Lost SSH connection/)).toBeNull();
    expect(screen.getByText('Stale')).toBeInTheDocument();

    // Server delete blocked with a reason, local delete unaffected.
    const serverDelete = screen.getByRole('button', {name: /Delete job_server_01/i});
    expect(serverDelete).toBeDisabled();
    expect(serverDelete.getAttribute('title')).toContain('SSH connection');
    expect(screen.getByRole('button', {name: /Delete job_local_01/i })).toBeEnabled();
  });

  it('blocks every delete when the backend is down', () => {
    useRemoteStore.setState({
      backendStatus: 'down',
      backendFailures: 1,
      backendLastError: 'Cannot reach NeuroFlow backend at http://127.0.0.1:8765: Failed to fetch',
      backendLastSeenAt: Date.now() - 120_000,
    });
    renderJobsPage('/jobs');

    expect(screen.getByRole('button', {name: /Delete job_server_01/i})).toBeDisabled();
    expect(screen.getByRole('button', {name: /Delete job_local_01/i })).toBeDisabled();
  });

  it('warns immediately on the first failure (no silent retry)', () => {
    useRemoteStore.setState({
      connected: true,
      sshStatus: 'disconnected',
      sshFailures: 1,
      sshLastError: 'transient failure',
      sshLastSeenAt: Date.now() - 60_000,
    });
    renderJobsPage('/jobs');

    expect(screen.getByText('Stale')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /Delete job_server_01/i })).toBeDisabled();
  });
});

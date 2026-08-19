import React from 'react';
import {describe, it, expect, beforeEach, vi} from 'vitest';
import {render, screen, fireEvent} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {JobsPage} from '../src/pages/JobsPage';
import {useJobsStore} from '../src/stores/jobsStore';

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

    expect(screen.getByText('Local Jobs')).toBeDefined();
    expect(screen.getByText('Server Jobs')).toBeDefined();

    // Check job cards exist
    expect(screen.getByText('job_local_01')).toBeDefined();
    expect(screen.getByText('job_local_02')).toBeDefined();
    expect(screen.getByText('job_server_01')).toBeDefined();
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
    expect(screen.getByText('Local Jobs')).toBeDefined();
    expect(screen.getByText('Server Jobs')).toBeDefined();
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
});


import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeAll, expect, test, vi} from 'vitest';
import {AppSidebar} from '../src/AppSidebar';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

function makeJob(overrides: Record<string, unknown> = {}) {
  return {
    job_id: `job-${Math.random().toString(36).slice(2, 8)}`,
    state: 'completed',
    started_at: Date.now() / 1000,
    target: 'Local',
    display_name: 'test-job',
    ...overrides,
  };
}

const defaultProps = {
  activeTab: 'jobs' as const,
  onSelectTab: vi.fn(),
  selectedJobId: null,
  onSelectJob: vi.fn(),
  sidebarOpen: true,
  onSidebarOpenChange: vi.fn(),
  sidebarWidth: 280,
  onSidebarWidthChange: vi.fn(),
};

test('shows only first 3 server jobs initially and hides the rest', () => {
  const serverJobs = [
    makeJob({job_id: 's1', target: 'Server', display_name: 'server-job-1', started_at: 4}),
    makeJob({job_id: 's2', target: 'Server', display_name: 'server-job-2', started_at: 3}),
    makeJob({job_id: 's3', target: 'Server', display_name: 'server-job-3', started_at: 2}),
    makeJob({job_id: 's4', target: 'Server', display_name: 'server-job-4', started_at: 1}),
  ];
  const localJobs = [makeJob({job_id: 'l1', target: 'Local', display_name: 'local-job-1'})];

  render(<AppSidebar {...defaultProps} jobs={[...serverJobs, ...localJobs]} />);

  expect(screen.getByText('server-job-1')).toBeInTheDocument();
  expect(screen.getByText('server-job-2')).toBeInTheDocument();
  expect(screen.getByText('server-job-3')).toBeInTheDocument();
  expect(screen.queryByText('server-job-4')).not.toBeInTheDocument();

  expect(screen.getByText(/View all server jobs/)).toBeInTheDocument();
  expect(screen.getByText(/1 more/)).toBeInTheDocument();
});

test('clicking "View all server jobs" reveals hidden jobs and changes label', async () => {
  const user = userEvent.setup();
  const serverJobs = [
    makeJob({job_id: 's1', target: 'Server', display_name: 'server-job-1', started_at: 4}),
    makeJob({job_id: 's2', target: 'Server', display_name: 'server-job-2', started_at: 3}),
    makeJob({job_id: 's3', target: 'Server', display_name: 'server-job-3', started_at: 2}),
    makeJob({job_id: 's4', target: 'Server', display_name: 'server-job-4', started_at: 1}),
  ];

  render(<AppSidebar {...defaultProps} jobs={serverJobs} />);

  expect(screen.queryByText('server-job-4')).not.toBeInTheDocument();

  await user.click(screen.getByText(/View all server jobs/));

  expect(screen.getByText('server-job-4')).toBeInTheDocument();
  expect(screen.getByText('Show fewer server jobs')).toBeInTheDocument();
  expect(screen.queryByText(/View all server jobs/)).not.toBeInTheDocument();
});

test('clicking "Show fewer server jobs" collapses the group again', async () => {
  const user = userEvent.setup();
  const serverJobs = [
    makeJob({job_id: 's1', target: 'Server', display_name: 'server-job-1', started_at: 4}),
    makeJob({job_id: 's2', target: 'Server', display_name: 'server-job-2', started_at: 3}),
    makeJob({job_id: 's3', target: 'Server', display_name: 'server-job-3', started_at: 2}),
    makeJob({job_id: 's4', target: 'Server', display_name: 'server-job-4', started_at: 1}),
  ];

  render(<AppSidebar {...defaultProps} jobs={serverJobs} />);

  await user.click(screen.getByText(/View all server jobs/));
  expect(screen.getByText('server-job-4')).toBeInTheDocument();

  await user.click(screen.getByText('Show fewer server jobs'));
  expect(screen.queryByText('server-job-4')).not.toBeInTheDocument();
  expect(screen.getByText(/View all server jobs/)).toBeInTheDocument();
  expect(screen.getByText(/1 more/)).toBeInTheDocument();
});

test('local jobs group is independent from server jobs group', async () => {
  const user = userEvent.setup();
  const serverJobs = [
    makeJob({job_id: 's1', target: 'Server', display_name: 'server-job-1', started_at: 6}),
    makeJob({job_id: 's2', target: 'Server', display_name: 'server-job-2', started_at: 5}),
    makeJob({job_id: 's3', target: 'Server', display_name: 'server-job-3', started_at: 4}),
    makeJob({job_id: 's4', target: 'Server', display_name: 'server-job-4', started_at: 3}),
  ];
  const localJobs = [
    makeJob({job_id: 'l1', target: 'Local', display_name: 'local-job-1', started_at: 2}),
    makeJob({job_id: 'l2', target: 'Local', display_name: 'local-job-2', started_at: 1}),
  ];

  render(<AppSidebar {...defaultProps} jobs={[...serverJobs, ...localJobs]} />);

  await user.click(screen.getByText(/View all server jobs/));

  expect(screen.getByText('server-job-4')).toBeInTheDocument();
  expect(screen.getByText('local-job-1')).toBeInTheDocument();
  expect(screen.getByText('local-job-2')).toBeInTheDocument();
});

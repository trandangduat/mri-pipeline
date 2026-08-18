import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeAll, expect, test, vi} from 'vitest';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router';
import {AppHeader} from '../src/components/AppHeader';
import {AppFooter} from '../src/components/AppFooter';

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

function renderHeader(props: {
  activeTab?: 'pipeline' | 'tools' | 'jobs';
  onSelectTab?: (tab: 'pipeline' | 'tools' | 'jobs') => void;
  jobsCount?: number;
} = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {queries: {retry: false}},
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AppHeader
          activeTab={props.activeTab || 'pipeline'}
          onSelectTab={props.onSelectTab || vi.fn()}
          jobsCount={props.jobsCount ?? 5}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('renders brand title and subtitle', () => {
  renderHeader();

  expect(screen.getByText('NeuroFlow')).toBeInTheDocument();
  expect(screen.getByText('MRI Pipeline')).toBeInTheDocument();
});

test('renders all 3 horizontal tabs with jobs count badge', () => {
  renderHeader({jobsCount: 42});

  expect(screen.getByText('Pipeline Configuration')).toBeInTheDocument();
  expect(screen.getByText('Tools Configuration')).toBeInTheDocument();
  expect(screen.getByText('Jobs Monitor')).toBeInTheDocument();
  expect(screen.getByText('42')).toBeInTheDocument();
});

test('triggers onSelectTab callback when clicking tabs', async () => {
  const user = userEvent.setup();
  const onSelectTab = vi.fn();

  renderHeader({activeTab: 'pipeline', onSelectTab});

  await user.click(screen.getByText('Tools Configuration'));
  expect(onSelectTab).toHaveBeenCalledWith('tools');

  await user.click(screen.getByText('Jobs Monitor'));
  expect(onSelectTab).toHaveBeenCalledWith('jobs');
});

test('renders workspace and pipeline action buttons', () => {
  renderHeader();

  expect(screen.getByText('Save Workspace')).toBeInTheDocument();
  expect(screen.getByText('Load Workspace')).toBeInTheDocument();
  expect(screen.getByText('Start Pipeline')).toBeInTheDocument();
  expect(screen.getByText('Stop Pipeline')).toBeInTheDocument();
});

test('renders AppFooter with system status, version, and links', () => {
  render(<AppFooter envText="python: ready · docker: ready" isReady={true} />);

  expect(screen.getByText(/NeuroFlow MRI Pipeline ©/)).toBeInTheDocument();
  expect(screen.getByText('System ready')).toBeInTheDocument();
  expect(screen.getByText('(python: ready · docker: ready)')).toBeInTheDocument();
  expect(screen.getByText('v1.0.0')).toBeInTheDocument();
  expect(screen.getByText('Documentation')).toBeInTheDocument();
  expect(screen.getByText('GitHub')).toBeInTheDocument();
});

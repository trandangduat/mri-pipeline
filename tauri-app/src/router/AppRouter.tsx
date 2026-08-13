import React, {useEffect, useCallback, useRef} from 'react';
import {HashRouter, Routes, Route, Navigate, useNavigate, useLocation} from 'react-router';
import {AppSidebar} from '../AppSidebar';
import {PipelinePage} from '../pages/PipelinePage';
import {ToolsPage} from '../pages/ToolsPage';
import {JobsPage} from '../pages/JobsPage';
import {useUiStore, type AppTab} from '../stores/uiStore';
import {useJobsStore} from '../stores/jobsStore';
import {useEnvironment, useClient} from '../query/useEnvironment';
import {usePipelineFormStore} from '../stores/pipelineFormStore';

function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const client = useClient();

  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const sidebarWidth = useUiStore((s) => s.sidebarWidth);
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen);
  const setSidebarWidth = useUiStore((s) => s.setSidebarWidth);
  const {data: environment} = useEnvironment();

  const setSelectedStatsAtlases = usePipelineFormStore((s) => s.setSelectedStatsAtlases);

  const latestJobs = useJobsStore((s) => s.latestJobs);
  const selectedJobId = useJobsStore((s) => s.selectedJobId);
  const appendOutput = useJobsStore((s) => s.appendOutput);

  const activeTab: AppTab = location.pathname.startsWith('/tools')
    ? 'tools'
    : location.pathname.startsWith('/jobs')
      ? 'jobs'
      : 'pipeline';

  const envParts = ['python', 'docker', 'ssh'].map((name) => {
    const item = (environment as Record<string, unknown> | undefined)?.[name] as {ok?: boolean} | undefined;
    return `${name}: ${item?.ok ? 'ready' : 'missing'}`;
  });

  const print = useCallback(
    (label: string, payload: unknown) => {
      const block = `${label}\n${JSON.stringify(payload, null, 2)}\n\n`;
      appendOutput(block);
    },
    [appendOutput],
  );

  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    (async () => {
      try {
        await client.waitForHealth();
        const meta = await client.metadata();
        if (meta?.stats_vectors) {
          const selection: Record<string, string[]> = {};
          for (const [statKey, stat] of Object.entries(meta.stats_vectors)) {
            const atlases = Array.isArray(stat.atlases) ? stat.atlases : [];
            selection[statKey] = statKey === 'cortical_thickness' ? atlases.slice(0, 2) : atlases.slice(0, 1);
          }
          setSelectedStatsAtlases(selection);
        }
      } catch (err: unknown) {
        print('Startup failed', {error: (err as Error)?.message});
      }
    })();
  }, [client, setSelectedStatsAtlases, print]);

  return (
    <main
      className="min-h-screen bg-cursor-canvas"
      id="appLayout"
      style={{'--active-sidebar-width': sidebarOpen ? `${sidebarWidth}px` : '3rem'} as React.CSSProperties}
    >
      <div
        id="sidebarRoot"
        className="fixed inset-y-0 left-0 z-30 w-[var(--active-sidebar-width)] max-[760px]:static max-[760px]:w-auto"
      >
        <AppSidebar
          activeTab={activeTab}
          onSelectTab={(tab) => navigate('/' + tab)}
          jobs={latestJobs}
          selectedJobId={selectedJobId}
          onSelectJob={(jobId) => navigate('/jobs/' + encodeURIComponent(jobId))}
          envText={envParts.join(' · ')}
          sidebarOpen={sidebarOpen}
          onSidebarOpenChange={setSidebarOpen}
          sidebarWidth={sidebarWidth}
          onSidebarWidthChange={setSidebarWidth}
        />
      </div>

      <section className="flex flex-col h-screen overflow-hidden min-w-0 px-6 py-4 ml-[var(--active-sidebar-width)] max-[760px]:ml-0 max-[760px]:px-4 max-[760px]:pb-4">
        <Routes>
          <Route path="/" element={<Navigate to="/pipeline" replace />} />
          <Route
            path="/pipeline"
            element={
              <section className="min-w-0 pl-16 max-[760px]:pl-0 block" data-page="pipeline">
                <PipelinePage />
              </section>
            }
          />
          <Route
            path="/tools"
            element={
              <section className="min-w-0 pl-16 max-[760px]:pl-0 block h-full overflow-y-auto" data-page="tools">
                <ToolsPage />
              </section>
            }
          />
          <Route
            path="/jobs"
            element={
              <section className="min-w-0 pl-16 max-[760px]:pl-0 block" data-page="jobs">
                <JobsPage />
              </section>
            }
          />
          <Route
            path="/jobs/:jobId"
            element={
              <section className="min-w-0 pl-16 max-[760px]:pl-0 block" data-page="jobs">
                <JobsPage />
              </section>
            }
          />
        </Routes>
      </section>
    </main>
  );
}

export function AppRouter() {
  return (
    <HashRouter>
      <AppLayout />
    </HashRouter>
  );
}

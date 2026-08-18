import React, {useEffect, useCallback, useRef} from 'react';
import {HashRouter, Routes, Route, Navigate, useNavigate, useLocation} from 'react-router';
import {AppHeader} from '../components/AppHeader';
import {AppFooter} from '../components/AppFooter';
import {PipelinePage} from '../pages/PipelinePage';
import {ToolsPage} from '../pages/ToolsPage';
import {JobsPage} from '../pages/JobsPage';
import type {AppTab} from '../stores/uiStore';
import {useJobsStore} from '../stores/jobsStore';
import {useEnvironment, useClient} from '../query/useEnvironment';
import {usePipelineFormStore} from '../stores/pipelineFormStore';

function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const client = useClient();

  const {data: environment} = useEnvironment();
  const setSelectedStatsAtlases = usePipelineFormStore((s) => s.setSelectedStatsAtlases);

  const latestJobs = useJobsStore((s) => s.latestJobs);
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

  const pythonOk = Boolean(
    (environment as Record<string, unknown> | undefined)?.python &&
      ((environment as Record<string, unknown> | undefined)?.python as {ok?: boolean}).ok,
  );
  const dockerOk = Boolean(
    (environment as Record<string, unknown> | undefined)?.docker &&
      ((environment as Record<string, unknown> | undefined)?.docker as {ok?: boolean}).ok,
  );
  const isEnvReady = pythonOk && dockerOk;

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
    <div className="h-screen w-screen overflow-hidden flex flex-col bg-cursor-canvas text-cursor-ink" id="appLayout">
      <AppHeader
        activeTab={activeTab}
        onSelectTab={(tab) => navigate('/' + tab)}
        jobsCount={latestJobs.length}
      />

      <main className="flex-1 min-h-0 w-full overflow-hidden flex flex-col">
        <Routes>
          <Route path="/" element={<Navigate to="/pipeline" replace />} />
          <Route
            path="/pipeline"
            element={
              <div className="w-full h-full min-h-0 flex flex-col" data-page="pipeline">
                <PipelinePage />
              </div>
            }
          />
          <Route
            path="/tools"
            element={
              <div className="w-full h-full min-h-0 flex flex-col" data-page="tools">
                <ToolsPage />
              </div>
            }
          />
          <Route
            path="/jobs"
            element={
              <div className="w-full h-full min-h-0 flex flex-col" data-page="jobs">
                <JobsPage />
              </div>
            }
          />
          <Route
            path="/jobs/:jobId"
            element={
              <div className="w-full h-full min-h-0 flex flex-col" data-page="jobs">
                <JobsPage />
              </div>
            }
          />
        </Routes>
      </main>

      <AppFooter envText={envParts.join(' · ')} isReady={isEnvReady} />
    </div>
  );
}

export function AppRouter() {
  return (
    <HashRouter>
      <AppLayout />
    </HashRouter>
  );
}

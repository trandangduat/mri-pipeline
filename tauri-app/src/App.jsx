import React, {useState} from 'react';
import {AppProvider, useApp} from './AppContext.jsx';
import {AppSidebar} from './AppSidebar.jsx';
import {PipelinePage} from './pages/PipelinePage.jsx';
import {ToolsPage} from './pages/ToolsPage.jsx';
import {JobsPage} from './pages/JobsPage.jsx';

function Shell() {
  const {activeTab, latestJobs, selectedJobId, switchTab, selectJob, environment} = useApp();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const envParts = ['python', 'docker', 'ssh'].map((name) => {
    const item = environment?.[name] || {ok: false};
    return `${name}: ${item.ok ? 'ready' : 'missing'}`;
  });

  return (
    <main
      className="min-h-screen bg-cursor-canvas"
      id="appLayout"
      style={{'--active-sidebar-width': sidebarOpen ? '16rem' : '3rem'}}
    >
      <div
        id="sidebarRoot"
        className="fixed inset-y-0 left-0 z-30 w-[var(--active-sidebar-width)] max-[760px]:static max-[760px]:w-auto"
      >
        <AppSidebar
          activeTab={activeTab}
          onSelectTab={switchTab}
          jobs={latestJobs}
          selectedJobId={selectedJobId}
          onSelectJob={(jobId) => selectJob(jobId)}
          envText={envParts.join(' · ')}
          sidebarOpen={sidebarOpen}
          onSidebarOpenChange={setSidebarOpen}
        />
      </div>

      <section className="grid min-h-screen min-w-0 px-8 py-8 ml-[var(--active-sidebar-width)] max-[760px]:ml-0 max-[760px]:px-4 max-[760px]:pb-4">
        <section className={`min-w-0 pl-8 max-[760px]:pl-0 ${activeTab === 'pipeline' ? 'block' : 'hidden'}`} data-page="pipeline">
          <PipelinePage />
        </section>
        <section className={`min-w-0 pl-8 max-[760px]:pl-0 ${activeTab === 'tools' ? 'block' : 'hidden'}`} data-page="tools">
          <ToolsPage />
        </section>
        <section className={`min-w-0 pl-8 max-[760px]:pl-0 ${activeTab === 'jobs' ? 'block' : 'hidden'}`} data-page="jobs">
          <JobsPage />
        </section>
      </section>
    </main>
  );
}

export function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}

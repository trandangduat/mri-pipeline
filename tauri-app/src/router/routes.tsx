import React from 'react';
import {Navigate, type RouteObject} from 'react-router';
import {PipelinePage} from '../pages/PipelinePage';
import {ToolsPage} from '../pages/ToolsPage';
import {JobsPage} from '../pages/JobsPage';

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Navigate to="/pipeline" replace />,
  },
  {
    path: '/pipeline',
    element: (
      <section className="min-w-0 pl-8 max-[760px]:pl-0 block" data-page="pipeline">
        <PipelinePage />
      </section>
    ),
  },
  {
    path: '/tools',
    element: (
      <section className="min-w-0 pl-8 max-[760px]:pl-0 block" data-page="tools">
        <ToolsPage />
      </section>
    ),
  },
  {
    path: '/jobs',
    element: (
      <section className="min-w-0 pl-8 max-[760px]:pl-0 block" data-page="jobs">
        <JobsPage />
      </section>
    ),
  },
  {
    path: '/jobs/:jobId',
    element: (
      <section className="min-w-0 pl-8 max-[760px]:pl-0 block" data-page="jobs">
        <JobsPage />
      </section>
    ),
  },
];

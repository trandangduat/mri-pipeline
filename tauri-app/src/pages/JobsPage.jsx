import React from 'react';
import {Download, Eraser, GitCommitHorizontal, LineChart, RefreshCw, Search, Square, Terminal, Trash2} from 'lucide-react';
import {Panel, Button, inputCls, StatusPill} from '../components/ui.jsx';
import {useApp} from '../AppContext.jsx';
import {formatDuration} from '../jobFormatters.js';
import {formatTime} from '../lib/format.js';
import {jobProgress, extractOutputFiles, progressStepEvents, stepEventState} from '../lib/jobs.js';

export function JobsPage() {
  const {latestJobs, selectedJobId, jobEvents, jobLogSearch, setJobLogSearch, outputText, clearJobLog, refreshJobs, print, busy} = useApp();

  const job = latestJobs.find((j) => j.job_id === selectedJobId) || null;
  const progress = jobProgress(job?.state, jobEvents.length);
  const events = progressStepEvents(jobEvents);
  const outputFiles = extractOutputFiles(jobEvents);
  const filteredLog = jobLogSearch.trim()
    ? outputText.split('\n').filter((line) => line.toLowerCase().includes(jobLogSearch.toLowerCase())).join('\n')
    : outputText;

  return (
    <div className="grid gap-6">
      <section className="grid gap-6 rounded-xl border border-cursor-hairline bg-white p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <span className="mb-2 block text-[11px] font-semibold uppercase leading-normal tracking-[0.88px] text-cursor-muted">Job Dashboard</span>
            <h2 className="m-0 text-2xl font-normal tracking-tight text-cursor-ink">{job?.display_name || job?.job_id || 'No job selected'}</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill state={job?.state || 'unknown'}>{(job?.state || 'unknown').toUpperCase()}</StatusPill>
            <span className="inline-flex items-center rounded-full border border-cursor-primary/20 bg-cursor-primary/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-primary">
              {job?.target || 'Local'}
            </span>
            <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-hairline-soft px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-ink">
              {job?.pipeline_mode || job?.mode || 'Preset unknown'}
            </span>
          </div>
        </div>

        <div className="grid gap-4 border-y border-cursor-hairline py-4 [grid-template-columns:repeat(auto-fit,minmax(10rem,1fr))]">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Job ID</span>
            <code className="w-fit rounded border border-cursor-hairline-soft bg-cursor-canvas-soft px-2 py-1 font-mono text-xs text-cursor-ink">{job?.job_id || 'None'}</code>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Started</span>
            <strong>{formatTime(job?.started_at)}</strong>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Duration</span>
            <strong>{formatDuration(job?.started_at, job?.finished_at)}</strong>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Process PID</span>
            <strong>{job?.pid || 'None'}</strong>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button id="refreshJobsButton" variant="primary" icon={<RefreshCw className="h-4 w-4" />} onClick={refreshJobs} disabled={busy.refreshJobs}>
            Refresh Jobs
          </Button>
          <Button variant="danger" icon={<Square className="h-4 w-4" />} onClick={() => print('Stop job', {ok: false, error: 'Select a running job in Jobs Monitor to stop it in a later slice.'})}>
            Stop Job
          </Button>
          <Button variant="ink" icon={<Download className="h-4 w-4" />} onClick={() => print('Download outputs', {ok: false, error: 'Download outputs is not implemented in this safety slice.'})}>
            Download Outputs
          </Button>
          <Button variant="ghost" icon={<Trash2 className="h-4 w-4" />} className="text-cursor-semantic-error hover:bg-cursor-canvas-soft" onClick={() => print('Delete job', {ok: false, error: 'Delete job is not implemented in this safety slice.'})}>
            Delete Job
          </Button>
        </div>
      </section>

      <div className="grid gap-6 grid-cols-2 max-[1080px]:grid-cols-1">
        <Panel icon={<GitCommitHorizontal className="h-5 w-5 text-cursor-primary" />} title="Execution Progress" titleRight={<span className="text-cursor-muted">{progress}%</span>}>
          <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-cursor-hairline-soft">
            <div className="h-full bg-cursor-primary transition-all duration-300" style={{width: `${progress}%`}} />
          </div>
          <div className="grid gap-3">
            {events.length ? (
              events.slice(-18).map((event, index) => (
                <div key={`${event.stage || event.step || event.kind || 'evt'}-${index}`} className="grid items-center gap-3 rounded-md border border-cursor-hairline-soft p-3 grid-cols-[6rem_minmax(0,1fr)_4rem]">
                  <StatusPill state={stepEventState(event)}>{stepEventState(event)}</StatusPill>
                  <strong>{event.stage || event.step || event.kind}</strong>
                  <span>{event.elapsed_sec ? `${event.elapsed_sec}s` : ''}</span>
                </div>
              ))
            ) : (
              <div className="mt-4 whitespace-pre-wrap rounded-lg border border-cursor-hairline bg-white p-4 text-cursor-body">
                {job ? 'No step events are available yet.' : 'Select a job from sidebar to view progress.'}
              </div>
            )}
          </div>
        </Panel>

        <Panel icon={<LineChart className="h-5 w-5 text-cursor-primary" />} title="Telemetry & Metrics" titleRight={<span className="text-cursor-muted">Real-time resource usage</span>}>
          <div className="grid grid-cols-3 gap-4 max-[1080px]:grid-cols-1">
            <Sparkline label="CPU Usage" points="0,35 20,30 40,18 60,26 80,12 100,19 120,8" />
            <Sparkline label="RAM Usage" points="0,33 20,31 40,28 60,22 80,17 100,15 120,13" />
            <Sparkline label="I/O Speed" points="0,36 20,36 40,32 60,34 80,20 100,21 120,16" />
          </div>
        </Panel>

        <Panel
          icon={<Terminal className="h-5 w-5 text-cursor-primary" />}
          title="Real-Time Terminal Log"
          titleRight={
            <div className="flex items-center gap-2">
              <label className="relative m-0 block w-full max-w-[14rem]">
                <input type="search" placeholder="Filter log output..." value={jobLogSearch} onChange={(e) => setJobLogSearch(e.target.value)} className={`${inputCls} pr-9`} />
                <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cursor-muted" />
              </label>
              <Button variant="ghost" icon={<Eraser className="h-4 w-4" />} onClick={clearJobLog}>
                Clear
              </Button>
            </div>
          }
        >
          <pre className="mt-2 min-h-72 max-h-[38rem] w-full overflow-auto whitespace-pre-wrap rounded-xl border border-cursor-hairline bg-white p-5 font-mono text-[13px] leading-[1.5] text-cursor-ink" aria-live="polite">
            {filteredLog || 'Log is empty.'}
          </pre>
        </Panel>

        <Panel icon={<Download className="h-5 w-5 text-cursor-primary" />} title="Artifacts & Outputs" titleRight={
          <Button variant="ink" onClick={() => print('Download selected outputs', {ok: false, error: 'Download outputs is not implemented in this safety slice.'})}>
            Download Selected
          </Button>
        }>
          <div className="mt-4 whitespace-pre-wrap rounded-lg border border-cursor-hairline bg-white p-4 text-cursor-body">
            {outputFiles.length ? outputFiles.join('\n') : `Output directory: ${job?.output_dir || job?.effective_output_dir || 'not reported'}`}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Sparkline({label, points}) {
  return (
    <div className="grid gap-3 rounded-lg border border-cursor-hairline-soft p-4 text-cursor-body">
      <span>{label}</span>
      <svg className="h-20 w-full" viewBox="0 0 120 42">
        <polyline className="fill-none stroke-cursor-primary stroke-2" points={points} />
      </svg>
    </div>
  );
}

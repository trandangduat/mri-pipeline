import {useEffect, useMemo, useRef, useState} from 'react';
import {ChevronRight, Download, Loader2, Search} from 'lucide-react';
import {toast} from 'sonner';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';
import {Button} from '@/components/ui/button';

interface ConsoleResponse {
  ok: boolean;
  error?: string;
  text: string;
  loading_older: boolean;
  download_available: boolean;
  records?: unknown[];
  supported_modes?: string[];
}

interface Props {
  jobId: string;
  remoteJobDir: string;
  isServer: boolean;
  running: boolean;
  subjectId: string;
  inputFile: string;
  remotePayload: object;
}

export function OperatorConsoleLog(props: Props) {
  const [expanded, setExpanded] = useState(false);
  const [viewMode, setViewMode] = useState<'summary' | 'detailed'>('summary');
  const [search, setSearch] = useState('');
  const [visibleText, setVisibleText] = useState('');
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadAvailable, setDownloadAvailable] = useState(true);
  const [error, setError] = useState('');
  const following = useRef(true);
  const latestText = useRef('');
  const backendMode = useRef<'combined' | 'summary'>('combined');
  const panel = useRef<HTMLDivElement>(null);
  const client = useMemo(() => new BackendClient(DEFAULT_BACKEND_URL), []);
  const endpoint = props.isServer ? '/remote/jobs/console' : '/jobs/local/console';
  const payloadKey = JSON.stringify(props.remotePayload);
  const payload = useMemo(() => ({
    ...(props.isServer ? JSON.parse(payloadKey) : {}),
    job_id: props.jobId,
    remote_job_dir: props.remoteJobDir,
    subject_id: props.subjectId,
    input_file: props.inputFile,
  }), [props.isServer, payloadKey, props.jobId, props.remoteJobDir, props.subjectId, props.inputFile]);

  useEffect(() => {
    if (!expanded) return;
    let disposed = false;
    let pending = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const load = async () => {
      if (pending || disposed) return;
      pending = true;
      setBusy(true);
      try {
        const requestedMode = viewMode === 'summary' ? 'summary' : backendMode.current;
        let response = await client.post(endpoint, {...payload, mode: requestedMode}, 30000, controller.signal) as ConsoleResponse;
        if (disposed) return;
        if (!response.ok) throw new Error(response.error || 'Subject log is unavailable.');
        // Older backends accept an unknown mode but return empty text.
        // Keep their valid subject activity visible during a frontend update.
        if (viewMode === 'detailed' && backendMode.current === 'combined' && !response.text &&
          (response.download_available || (response.records?.length || 0) > 0)) {
          backendMode.current = 'summary';
          response = await client.post(endpoint, {...payload, mode: 'summary'}, 30000, controller.signal) as ConsoleResponse;
        } else if (viewMode === 'detailed' && backendMode.current === 'summary' && response.supported_modes?.includes('combined')) {
          backendMode.current = 'combined';
          response = await client.post(endpoint, {...payload, mode: 'combined'}, 30000, controller.signal) as ConsoleResponse;
        }
        if (disposed) return;
        if (!response.ok) throw new Error(response.error || 'Subject log is unavailable.');
        if (viewMode === 'summary' && response.supported_modes?.includes('combined')) backendMode.current = 'combined';
        setError('');
        setDownloadAvailable(response.download_available);
        const text = viewMode === 'detailed' && backendMode.current === 'summary'
          ? `[Note] Restart NeuroFlow to include tool output.\n\n${response.text}`
          : response.text;
        latestText.current = text;
        if (following.current) setVisibleText(text);
        if (props.running || response.loading_older) timer = setTimeout(() => void load(), response.loading_older ? 500 : 10000);
      } catch (caught) {
        if (disposed) return;
        setError(caught instanceof Error ? caught.message : 'Cannot read subject log.');
        if (props.running) timer = setTimeout(() => void load(), 10000);
      } finally {
        pending = false;
        if (!disposed) setBusy(false);
      }
    };
    void load();
    return () => { disposed = true; controller.abort(); if (timer) clearTimeout(timer); };
  }, [client, endpoint, payload, expanded, props.running, viewMode]);

  useEffect(() => {
    if (following.current && panel.current) panel.current.scrollTop = panel.current.scrollHeight;
  }, [visibleText, error, search]);

  const searchText = search.trim().toLowerCase();
  const sourceLines = useMemo(() => visibleText ? visibleText.split('\n') : [], [visibleText]);
  const displayedLines = sourceLines.map((text, index) => ({number: index + 1, text}))
    .filter(line => !searchText || line.text.toLowerCase().includes(searchText));
  const rows: {number: number | null; text: string}[] = displayedLines.length ? displayedLines : [{
    number: null,
    text: visibleText ? 'No matching log lines.' : busy ? 'Loading subject log...' : 'No subject log is available.',
  }];
  if (error) {
    ['', `[Connection] ${error}`].join('\n').split('\n').forEach((text, index) => {
      rows.push({number: sourceLines.length + index + 1, text});
    });
  }
  const numberWidth = Math.max(2, String(sourceLines.length + (error ? error.split('\n').length + 1 : 0)).length);
  const switchView = (next: 'summary' | 'detailed') => {
    if (next === viewMode) return;
    following.current = true;
    latestText.current = '';
    setVisibleText('');
    setError('');
    setBusy(true);
    setViewMode(next);
  };

  const download = async () => {
    setDownloading(true);
    try {
      const {save} = await import('@tauri-apps/plugin-dialog');
      const target = await save({title: 'Save subject log',
        defaultPath: `${props.subjectId.replace(/[^A-Za-z0-9_.-]/g, '_')}.log`,
        filters: [{name: 'Log file', extensions: ['log']}]});
      if (!target) return;
      const result = await client.post(endpoint + '/export', {...payload, target_file: target}, 300000) as {ok: boolean; error?: string};
      if (!result.ok) throw new Error(result.error || 'Log download failed.');
      toast.success('Subject log saved.');
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : 'Log download failed.');
    } finally { setDownloading(false); }
  };

  return <div className="bg-cursor-surface-card border border-cursor-hairline rounded-lg p-3.5 shadow-none flex flex-col min-h-0">
    <div className="flex items-center justify-between gap-2">
      <button type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}
        className="flex items-center gap-1.5 text-sm font-semibold text-cursor-ink bg-transparent border-none p-0 cursor-pointer">
        <ChevronRight className={`h-4 w-4 transition-transform ${expanded ? 'rotate-90' : ''}`} />Log
      </button>
      <Button size="sm" variant="outline" onClick={() => void download()} disabled={downloading || !downloadAvailable}
        title="Save all available logs for this subject, including earlier output and all recorded attempts." className="h-6 px-2 text-2xs">
        {downloading ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Download className="h-3 w-3 mr-1" />}Download
      </Button>
    </div>
    {expanded && <>
      <div className="mt-2.5 flex items-center gap-1.5">
        <div role="group" aria-label="Log detail" className="flex items-center gap-1">
          {(['summary', 'detailed'] as const).map(mode => <Button key={mode} size="sm"
            variant={viewMode === mode ? 'default' : 'outline'} aria-pressed={viewMode === mode}
            onClick={() => switchView(mode)} className="h-6 px-2 text-2xs capitalize">{mode}</Button>)}
        </div>
        <label className="relative ml-auto min-w-0 max-w-36">
          <Search className="absolute left-1.5 top-1/2 h-3 w-3 -translate-y-1/2 text-cursor-muted pointer-events-none" />
          <input type="search" aria-label="Search displayed log lines" title="Search the displayed log lines"
            placeholder="Search..." value={search} onChange={event => setSearch(event.target.value)}
            className="h-6 w-full rounded-md border border-cursor-hairline bg-cursor-surface-card py-0.5 pl-6 pr-2 text-2xs" />
        </label>
      </div>
      <div ref={panel} role="log" aria-label="Subject log" aria-live={following.current ? 'polite' : 'off'}
      onScroll={() => {
        const element = panel.current;
        if (!element) return;
        following.current = element.scrollHeight - element.scrollTop - element.clientHeight <= 24;
        if (following.current) setVisibleText(latestText.current);
      }} className="mt-2.5 max-h-[24rem] min-h-[10rem] overflow-auto rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft py-2.5 text-xs leading-relaxed text-cursor-ink font-mono">
        <div className="grid" style={{gridTemplateColumns: `calc(${numberWidth}ch + 1rem) minmax(0, 1fr)`}}>
          {rows.map(line => <div key={line.number ?? 'placeholder'} className="contents">
            <span aria-hidden="true" className="select-none border-r border-cursor-hairline-soft bg-cursor-canvas-soft px-2 text-right tabular-nums text-cursor-muted">
              {line.number ?? ''}
            </span>
            <span className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere] px-2.5">{line.text || '\u00a0'}</span>
          </div>)}
        </div>
      </div>
    </>}
  </div>;
}

import React, {useRef, useEffect} from 'react';
import {ChevronDown, ChevronRight, AlertCircle, Terminal} from 'lucide-react';
import {Button, StatusPill} from './ui';
import type {ImageDownloadState} from '../stores/toolsStore';

interface DownloadProgressProps {
  image: string;
  state: ImageDownloadState;
  onClear: () => void;
}

export function DownloadProgress({image, state, onClear}: DownloadProgressProps) {
  const [expanded, setExpanded] = React.useState(false);
  const logRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (logRef.current && expanded) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [state.logs, expanded]);

  if (state.status === 'idle') return null;

  const shortImage = image.split('/').pop() || image;

  return (
    <div className="rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Terminal className="h-4 w-4 flex-none text-cursor-muted" />
          <code className="truncate font-mono text-xs text-cursor-ink">{shortImage}</code>
          <StatusPill state={state.status === 'pulling' ? 'running' : state.status}>
            {state.status === 'pulling' ? 'Pulling' : state.status === 'success' ? 'Done' : 'Failed'}
          </StatusPill>
        </div>
        <div className="flex items-center gap-1">
          {state.status === 'failed' && state.error && (
            <span className="max-w-[200px] truncate text-xs text-cursor-semantic-error">{state.error}</span>
          )}
          <button
            className="flex h-6 w-6 items-center justify-center rounded-md text-cursor-muted hover:bg-cursor-hairline-soft hover:text-cursor-ink"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </button>
          {(state.status === 'success' || state.status === 'failed') && (
            <Button variant="ghost" className="h-6 px-2 text-[11px]" onClick={onClear}>
              Dismiss
            </Button>
          )}
        </div>
      </div>

      {expanded && state.logs.length > 0 && (
        <pre
          ref={logRef}
          className="mt-2 max-h-48 overflow-auto rounded-md border border-cursor-hairline-soft bg-white p-2 font-mono text-[11px] leading-relaxed text-cursor-body"
        >
          {state.logs.join('\n')}
        </pre>
      )}

      {state.status === 'failed' && state.error && !expanded && (
        <div className="mt-2 flex items-start gap-1.5 rounded-md border border-cursor-semantic-error/20 bg-cursor-semantic-error/5 p-2">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-none text-cursor-semantic-error" />
          <span className="text-xs text-cursor-semantic-error">{state.error}</span>
        </div>
      )}
    </div>
  );
}

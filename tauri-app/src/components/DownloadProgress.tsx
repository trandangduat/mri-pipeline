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
    <div className="rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft p-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Terminal className="h-3.5 w-3.5 flex-none text-cursor-muted" />
          <code className="truncate font-mono text-xs text-cursor-ink">{shortImage}</code>
          <StatusPill state={state.status === 'pulling' ? 'running' : state.status}>
            {state.status === 'pulling' ? 'Pulling' : state.status === 'success' ? 'Done' : 'Failed'}
          </StatusPill>
        </div>
        <div className="flex items-center gap-1">
          {state.status === 'failed' && state.error && (
            <span className="max-w-[180px] truncate text-xs text-cursor-semantic-error">{state.error}</span>
          )}
          <button
            className="flex h-5.5 w-5.5 items-center justify-center rounded text-cursor-muted hover:bg-cursor-hairline-soft hover:text-cursor-ink"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
          {(state.status === 'success' || state.status === 'failed') && (
            <Button variant="ghost" className="h-5.5 px-1.5 text-2xs" onClick={onClear}>
              Dismiss
            </Button>
          )}
        </div>
      </div>

      {expanded && state.logs.length > 0 && (
        <pre
          ref={logRef}
          className="mt-1.5 max-h-40 overflow-auto rounded border border-cursor-hairline-soft bg-cursor-surface-card p-2 font-mono text-2xs leading-relaxed text-cursor-body"
        >
          {state.logs.join('\n')}
        </pre>
      )}

      {state.status === 'failed' && state.error && !expanded && (
        <div className="mt-1.5 flex items-start gap-1 rounded border border-cursor-semantic-error/20 bg-cursor-semantic-error/5 p-1.5">
          <AlertCircle className="mt-0.5 h-3 w-3 flex-none text-cursor-semantic-error" />
          <span className="text-xs text-cursor-semantic-error">{state.error}</span>
        </div>
      )}
    </div>
  );
}

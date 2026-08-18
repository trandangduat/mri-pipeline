import React from 'react';
import {ExternalLink} from 'lucide-react';

export interface AppFooterProps {
  envText?: string;
  isReady?: boolean;
}

export function AppFooter({envText, isReady = true}: AppFooterProps) {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="sticky bottom-0 z-30 flex h-10 w-full flex-none items-center justify-between border-t border-cursor-hairline bg-cursor-canvas px-6 text-xs text-cursor-body">
      <div className="flex items-center gap-2">
        <span>NeuroFlow MRI Pipeline © {currentYear}</span>
      </div>

      <div className="flex items-center gap-2" title={envText || 'Environment status'}>
        <span
          className={`h-2 w-2 rounded-full ${
            isReady ? 'bg-cursor-semantic-success' : 'bg-cursor-semantic-error'
          }`}
        />
        <span className="font-medium text-cursor-ink">
          {isReady ? 'System ready' : 'Environment incomplete'}
        </span>
        {envText ? <span className="text-cursor-muted">({envText})</span> : null}
      </div>

      <div className="flex items-center gap-4 text-cursor-body">
        <span className="font-mono text-[11px] text-cursor-muted">v1.0.0</span>
        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 hover:text-cursor-ink transition-colors"
        >
          Documentation
          <ExternalLink className="h-3 w-3" />
        </a>
        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 hover:text-cursor-ink transition-colors"
        >
          GitHub
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </footer>
  );
}

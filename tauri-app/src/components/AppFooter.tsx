import React from 'react';
import {ExternalLink} from 'lucide-react';

export interface AppFooterProps {
  isReady?: boolean;
  /** Live connection warning (backend/SSH down). Overrides the ready label. */
  connectionLabel?: string | null;
}

export function AppFooter({isReady = true, connectionLabel}: AppFooterProps) {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="sticky bottom-0 z-30 flex h-7.5 w-full flex-none items-center justify-between border-t border-cursor-hairline bg-cursor-canvas px-4 text-xs text-cursor-body">
      <div className="flex items-center gap-1.5">
        <span>NeuroFlow MRI Pipeline © {currentYear}</span>
      </div>

      <div className="flex items-center gap-1.5">
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            connectionLabel
              ? 'bg-cursor-semantic-error'
              : isReady
                ? 'bg-cursor-semantic-success'
                : 'bg-cursor-semantic-error'
          }`}
        />
        <span className="font-medium text-cursor-ink">
          {connectionLabel ?? (isReady ? 'System ready' : 'Environment incomplete')}
        </span>
      </div>

      <div className="flex items-center gap-3 text-cursor-body">
        <span className="font-mono text-2xs text-cursor-muted">v1.0.0</span>
        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 hover:text-cursor-ink transition-colors"
        >
          Documentation
          <ExternalLink className="h-2.5 w-2.5" />
        </a>
        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 hover:text-cursor-ink transition-colors"
        >
          GitHub
          <ExternalLink className="h-2.5 w-2.5" />
        </a>
      </div>
    </footer>
  );
}

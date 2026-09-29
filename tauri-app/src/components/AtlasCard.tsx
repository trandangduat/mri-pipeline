import React from 'react';
import {Layers, Download, CheckCircle2, AlertCircle, Loader2, RotateCw} from 'lucide-react';
import {Button} from './ui';
import type {AtlasPack} from '../types/backend';
import {cn} from '@/lib/utils';

interface AtlasCardProps {
  pack: AtlasPack;
  onDownload: (packId: string) => void;
  isDownloading?: boolean | undefined;
  downloadState?:
    | {
        status: 'idle' | 'connecting' | 'downloading' | 'extracting' | 'success' | 'failed';
        percent: number;
        message: string;
        error: string | null;
      }
    | undefined;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AtlasCard({pack, onDownload, isDownloading, downloadState}: AtlasCardProps) {
  const isInstalled = pack.installed;
  const isFailed = downloadState?.status === 'failed';
  const isCurrentDownloading = Boolean(
    !isFailed &&
      (isDownloading ||
        (downloadState &&
          ['connecting', 'downloading', 'extracting'].includes(downloadState.status))),
  );

  return (
    <div className="flex flex-col justify-between rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 transition-all hover:border-cursor-hairline-strong hover:shadow-xs min-h-[170px]">
      <div>
        {/* Header: Icon + Name + Default Badge */}
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <div
              className={cn(
                'flex h-7 w-7 flex-none items-center justify-center rounded-md',
                isInstalled
                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
                  : 'bg-cursor-canvas-soft text-cursor-muted',
              )}
            >
              <Layers className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-cursor-ink" title={pack.label}>
                {pack.label}
              </span>
              <span className="block truncate font-mono text-2xs text-cursor-muted-soft">
                {pack.id}
              </span>
            </div>
          </div>
          {pack.is_default && (
            <span className="flex-none rounded bg-cursor-primary/10 px-1.5 py-0.5 text-2xs font-semibold text-cursor-primary">
              Default
            </span>
          )}
        </div>

        {/* Description */}
        <p className="mb-2.5 text-xs text-cursor-muted leading-relaxed line-clamp-2">
          {pack.description}
        </p>
      </div>

      <div>
        {/* Meta Info */}
        <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-2xs text-cursor-body">
          <span className="text-cursor-muted">
            {pack.files.length} file{pack.files.length !== 1 ? 's' : ''}
          </span>
          <span className="text-cursor-muted-soft">•</span>
          <span className="text-cursor-muted" title={`Uncompressed: ${formatBytes(pack.uncompressed_size_bytes)}`}>
            {formatBytes(pack.compressed_size_bytes)} download
          </span>
        </div>

        {/* Progress bar if downloading */}
        {isCurrentDownloading && downloadState && (
          <div className="mb-2.5 space-y-1">
            <div className="flex items-center justify-between text-2xs text-cursor-muted">
              <span className="flex items-center gap-1">
                <Loader2 className="h-3 w-3 animate-spin text-cursor-primary" />
                {downloadState.message || 'Downloading...'}
              </span>
              <span>{downloadState.percent}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-cursor-canvas-soft">
              <div
                className="h-full bg-cursor-primary transition-all duration-300"
                style={{width: `${downloadState.percent}%`}}
              />
            </div>
          </div>
        )}

        {/* Error message if failed */}
        {isFailed && downloadState?.error && (
          <div className="mb-2.5 flex items-start gap-1 rounded bg-cursor-semantic-error/10 p-1.5 text-2xs text-cursor-semantic-error">
            <AlertCircle className="h-3.5 w-3.5 flex-none mt-0.5" />
            <span className="line-clamp-2">{downloadState.error}</span>
          </div>
        )}

        {/* Bottom Actions Row */}
        <div className="flex items-center justify-between border-t border-cursor-hairline pt-2">
          <div>
            {isInstalled ? (
              <span className="flex items-center gap-1 text-2xs font-medium text-cursor-semantic-success">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Installed
              </span>
            ) : (
              <span className="flex items-center gap-1 text-2xs font-medium text-amber-500">
                <AlertCircle className="h-3.5 w-3.5" />
                Not installed
              </span>
            )}
          </div>

          <div>
            {isCurrentDownloading ? (
              <Button variant="ghost" disabled className="h-7 px-2.5 text-xs">
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                Downloading
              </Button>
            ) : isFailed ? (
              <Button
                variant="base"
                className="h-7 px-2.5 text-xs text-cursor-semantic-error border border-cursor-semantic-error/30 hover:bg-cursor-semantic-error/10"
                onClick={() => onDownload(pack.id)}
              >
                <RotateCw className="mr-1 h-3 w-3" />
                Retry
              </Button>
            ) : isInstalled ? (
              <Button
                variant="ghost"
                className="h-7 px-2.5 text-xs text-cursor-muted hover:text-cursor-ink"
                onClick={() => onDownload(pack.id)}
                title="Re-download and overwrite existing atlas files"
              >
                <RotateCw className="mr-1 h-3 w-3" />
                Re-download
              </Button>
            ) : (
              <Button
                variant="primary"
                className="h-7 px-2.5 text-xs"
                onClick={() => onDownload(pack.id)}
              >
                <Download className="mr-1 h-3 w-3" />
                Download
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

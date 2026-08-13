import React from 'react';
import {Download, Loader2, Trash2, HardDrive, Package, Container, RefreshCw} from 'lucide-react';
import {Button} from './ui';
import type {ToolImage} from '../types/backend';
import {isImageDownloading, isImageFailed} from '../lib/tools';

interface InstalledCardProps {
  image: ToolImage;
  target?: string;
  onRemove?: (image: string) => void;
  isRemoving?: boolean;
}

export function InstalledImageCard({image, target, onRemove, isRemoving}: InstalledCardProps) {
  const toolDetails = image.tool_details || [];
  const tag = image.image.split(':').pop() || 'latest';
  const repo = image.image.split(':')[0];

  return (
    <div className="flex flex-col rounded-xl border border-cursor-hairline bg-white p-5">
      <div className="mb-3 flex items-start gap-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="flex h-10 w-10 flex-none items-center justify-center rounded-lg bg-cursor-semantic-success/10">
            <Container className="h-5 w-5 text-cursor-semantic-success" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center gap-2">
              <code className="break-all font-mono text-base font-medium text-cursor-ink">{repo}</code>
              <span className="flex-none rounded-md bg-cursor-canvas-soft px-2 py-0.5 font-mono text-[11px] text-cursor-muted">
                :{tag}
              </span>
            </div>
            {image.image_id && (
              <code className="font-mono text-[11px] text-cursor-muted-soft">{image.image_id}</code>
            )}
          </div>
        </div>
      </div>

      <div className="mb-3 text-xs text-cursor-body">
        Docker image for {toolDetails.length || image.tools.length} tool{((toolDetails.length || image.tools.length) !== 1) ? 's' : ''}
      </div>

      <div className="mb-4 flex flex-wrap gap-4">
        {target && (
          <div className="flex items-center gap-1.5 text-xs text-cursor-body">
            <span className="text-cursor-muted">Target:</span>
            <span className="font-mono text-cursor-ink">{target}</span>
          </div>
        )}
        <div className="flex items-center gap-1.5 text-xs text-cursor-body">
          <HardDrive className="h-3.5 w-3.5 text-cursor-muted" />
          <span className="text-cursor-muted">Size:</span>
          <span className="font-mono text-cursor-ink">{image.repo_size || '—'}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-cursor-body">
          <Package className="h-3.5 w-3.5 text-cursor-muted" />
          <span className="text-cursor-muted">Uncompressed:</span>
          <span className="font-mono text-cursor-ink">{image.uncompressed_size || '—'}</span>
        </div>
      </div>

      {toolDetails.length > 0 && (
        <div className="mb-4">
          <div className="flex flex-wrap gap-1.5">
            {toolDetails.map((tool) => (
              <span
                key={tool.key}
                className="inline-flex rounded-md bg-cursor-canvas-soft px-2 py-0.5 text-xs text-cursor-ink"
              >
                {tool.name}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-auto pt-2">
        <Button
          variant="ghost"
          icon={isRemoving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
          className="border-cursor-semantic-error/30 text-cursor-semantic-error hover:bg-cursor-semantic-error/5"
          disabled={isRemoving}
          onClick={() => onRemove?.(image.image)}
        >
          {isRemoving ? 'Removing...' : 'Remove Image'}
        </Button>
      </div>
    </div>
  );
}

interface MissingCardProps {
  image: ToolImage;
  target?: string;
  isDownloading?: boolean;
  isFrontendPulling?: boolean;
  onDownload?: (image: string) => void;
  maxToolChips?: number;
}

export function MissingImageCard({image, target, isDownloading, isFrontendPulling, onDownload, maxToolChips = 4}: MissingCardProps) {
  const toolDetails = image.tool_details || [];
  const tag = image.image.split(':').pop() || 'latest';
  const repo = image.image.split(':')[0];
  const downloading = isDownloading || isFrontendPulling;
  const failed = isImageFailed(image);
  const visibleTools = toolDetails.slice(0, maxToolChips);
  const extraCount = toolDetails.length - maxToolChips;

  return (
    <div className="flex flex-col rounded-xl border border-cursor-hairline bg-white p-5">
      <div className="mb-3 flex items-start gap-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="flex h-10 w-10 flex-none items-center justify-center rounded-lg bg-cursor-semantic-error/10">
            <Container className="h-5 w-5 text-cursor-semantic-error" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <code className="break-all font-mono text-base font-medium text-cursor-ink">{repo}</code>
              <span className="flex-none rounded-md bg-cursor-canvas-soft px-2 py-0.5 font-mono text-[11px] text-cursor-muted">
                :{tag}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="mb-3 text-xs text-cursor-body">
        Docker image for {toolDetails.length || image.tools.length} tool{((toolDetails.length || image.tools.length) !== 1) ? 's' : ''}
      </div>

      <div className="mb-3 flex flex-wrap gap-4">
        {target && (
          <div className="flex items-center gap-1.5 text-xs text-cursor-body">
            <span className="text-cursor-muted">Target:</span>
            <span className="font-mono text-cursor-ink">{target}</span>
          </div>
        )}
        {image.repo_size && (
          <div className="flex items-center gap-1.5 text-xs text-cursor-body">
            <HardDrive className="h-3.5 w-3.5 text-cursor-muted" />
            <span className="text-cursor-muted">Size:</span>
            <span className="font-mono text-cursor-ink">{image.repo_size}</span>
          </div>
        )}
      </div>

      {visibleTools.length > 0 && (
        <div className="mb-4">
          <div className="flex flex-wrap gap-1.5">
            {visibleTools.map((tool) => (
              <span
                key={tool.key}
                className="inline-flex rounded-md bg-cursor-canvas-soft px-2 py-0.5 text-xs text-cursor-ink"
              >
                {tool.name}
              </span>
            ))}
            {extraCount > 0 && (
              <span className="inline-flex rounded-md bg-cursor-hairline px-2 py-0.5 text-xs text-cursor-muted">
                +{extraCount} more
              </span>
            )}
          </div>
        </div>
      )}

      <div className="mt-auto pt-2">
        <Button
          variant="primary"
          icon={downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : failed ? <RefreshCw className="h-4 w-4" /> : <Download className="h-4 w-4" />}
          disabled={downloading}
          className="w-full"
          onClick={() => onDownload?.(image.image)}
        >
          {downloading ? 'Downloading...' : failed ? 'Retry Download' : 'Download Image'}
        </Button>
      </div>
    </div>
  );
}

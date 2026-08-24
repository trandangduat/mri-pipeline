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
  maxToolChips?: number;
}

export function InstalledImageCard({
  image,
  target,
  onRemove,
  isRemoving,
  maxToolChips = 4,
}: InstalledCardProps) {
  const toolDetails = image.tool_details || [];
  const repo = image.image.split(':')[0] || image.image;
  const visibleTools = toolDetails.slice(0, maxToolChips);
  const extraCount = toolDetails.length - maxToolChips;

  return (
    <div className="flex flex-col rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 transition-all hover:border-cursor-hairline-strong hover:shadow-xs min-h-[160px]">
      {/* Header: Icon + Repo name */}
      <div className="mb-2 flex items-center gap-2">
        <div className="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-cursor-semantic-success/10">
          <Container className="h-4 w-4 text-cursor-semantic-success" />
        </div>
        <div className="min-w-0 flex-1">
          <span
            className="block truncate text-base font-semibold text-cursor-ink"
            title={image.image}
          >
            {repo}
          </span>
          {image.image_id && (
            <span className="block truncate font-mono text-2xs text-cursor-muted-soft">
              {image.image_id}
            </span>
          )}
        </div>
      </div>

      {/* Subtitle / Meta row */}
      <div className="mb-2 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-cursor-body">
        <span className="text-cursor-muted">
          {toolDetails.length || image.tools.length} tool{((toolDetails.length || image.tools.length) !== 1) ? 's' : ''}
        </span>
        {target && (
          <div className="flex items-center gap-1">
            <span className="text-cursor-muted">Target:</span>
            <span className="font-mono text-cursor-ink">{target}</span>
          </div>
        )}
        {image.repo_size && (
          <div className="flex items-center gap-1">
            <HardDrive className="h-3 w-3 text-cursor-muted" />
            <span className="font-mono text-cursor-ink">{image.repo_size}</span>
          </div>
        )}
        {image.uncompressed_size && (
          <div className="flex items-center gap-1">
            <Package className="h-3 w-3 text-cursor-muted" />
            <span className="font-mono text-cursor-ink">{image.uncompressed_size}</span>
          </div>
        )}
      </div>

      {/* Tool Chips */}
      {visibleTools.length > 0 && (
        <div className="mb-2.5">
          <div className="flex flex-wrap gap-1">
            {visibleTools.map((tool) => (
              <span
                key={tool.key}
                className="inline-flex items-center rounded border border-cursor-hairline-soft bg-cursor-canvas-soft px-1.5 py-0.25 text-2xs font-medium text-cursor-ink max-w-full truncate"
              >
                {tool.name}
              </span>
            ))}
            {extraCount > 0 && (
              <span
                title={toolDetails.slice(maxToolChips).map((t) => t.name).join(', ')}
                className="inline-flex cursor-help items-center rounded border border-cursor-hairline bg-cursor-canvas px-1.5 py-0.25 text-2xs font-medium text-cursor-muted"
              >
                +{extraCount} more
              </span>
            )}
          </div>
        </div>
      )}

      {/* Footer action button */}
      <div className="mt-auto pt-2 border-t border-cursor-hairline-soft">
        <Button
          variant="ghost"
          icon={isRemoving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
          className="w-full border border-cursor-semantic-error/20 text-cursor-semantic-error hover:bg-cursor-semantic-error/5 hover:border-cursor-semantic-error/40"
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

export function MissingImageCard({
  image,
  target,
  isDownloading,
  isFrontendPulling,
  onDownload,
  maxToolChips = 4,
}: MissingCardProps) {
  const toolDetails = image.tool_details || [];
  const repo = image.image.split(':')[0] || image.image;
  const downloading = isDownloading || isFrontendPulling;
  const failed = isImageFailed(image);
  const visibleTools = toolDetails.slice(0, maxToolChips);
  const extraCount = toolDetails.length - maxToolChips;

  return (
    <div className="flex flex-col rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 transition-all hover:border-cursor-hairline-strong hover:shadow-xs min-h-[160px]">
      {/* Header: Icon + Repo name */}
      <div className="mb-2 flex items-center gap-2">
        <div className="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-cursor-semantic-error/10">
          <Container className="h-4 w-4 text-cursor-semantic-error" />
        </div>
        <div className="min-w-0 flex-1">
          <span
            className="block truncate text-base font-semibold text-cursor-ink"
            title={image.image}
          >
            {repo}
          </span>
        </div>
      </div>

      {/* Subtitle / Meta row */}
      <div className="mb-2 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-cursor-body">
        <span className="text-cursor-muted">
          {toolDetails.length || image.tools.length} tool{((toolDetails.length || image.tools.length) !== 1) ? 's' : ''}
        </span>
        {target && (
          <div className="flex items-center gap-1">
            <span className="text-cursor-muted">Target:</span>
            <span className="font-mono text-cursor-ink">{target}</span>
          </div>
        )}
        {image.repo_size && (
          <div className="flex items-center gap-1">
            <HardDrive className="h-3 w-3 text-cursor-muted" />
            <span className="font-mono text-cursor-ink">{image.repo_size}</span>
          </div>
        )}
      </div>

      {/* Tool Chips */}
      {visibleTools.length > 0 && (
        <div className="mb-2.5">
          <div className="flex flex-wrap gap-1">
            {visibleTools.map((tool) => (
              <span
                key={tool.key}
                className="inline-flex items-center rounded border border-cursor-hairline-soft bg-cursor-canvas-soft px-1.5 py-0.25 text-2xs font-medium text-cursor-ink max-w-full truncate"
              >
                {tool.name}
              </span>
            ))}
            {extraCount > 0 && (
              <span
                title={toolDetails.slice(maxToolChips).map((t) => t.name).join(', ')}
                className="inline-flex cursor-help items-center rounded border border-cursor-hairline bg-cursor-canvas px-1.5 py-0.25 text-2xs font-medium text-cursor-muted"
              >
                +{extraCount} more
              </span>
            )}
          </div>
        </div>
      )}

      {/* Footer action button */}
      <div className="mt-auto pt-2 border-t border-cursor-hairline-soft">
        <Button
          variant="primary"
          icon={downloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : failed ? <RefreshCw className="h-3.5 w-3.5" /> : <Download className="h-3.5 w-3.5" />}
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

import React from 'react';
import {Download, Loader2, Trash2, HardDrive, Package} from 'lucide-react';
import {Button, StatusPill} from './ui';
import type {ToolImage} from '../types/backend';
import {isImageInstalled} from '../lib/tools';

interface ImageCardProps {
  image: ToolImage;
  onRemove?: (image: string) => void;
  onDownload?: (image: string) => void;
  isRemoving?: boolean;
  isDownloading?: boolean;
}

export function ImageCard({image, onRemove, onDownload, isRemoving, isDownloading}: ImageCardProps) {
  const installed = isImageInstalled(image);
  const toolDetails = image.tool_details || [];
  const tag = image.image.split(':').pop() || 'latest';
  const repo = image.image.split(':')[0];

  return (
    <div className="rounded-xl border border-cursor-hairline bg-white p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <code className="truncate font-mono text-sm font-medium text-cursor-ink">{repo}</code>
            <span className="flex-none rounded-md bg-cursor-canvas-soft px-2 py-0.5 font-mono text-[11px] text-cursor-muted">
              :{tag}
            </span>
          </div>
          {image.image_id && (
            <code className="font-mono text-[11px] text-cursor-muted-soft">{image.image_id}</code>
          )}
        </div>
        <StatusPill state={installed ? 'installed' : 'missing'}>{installed ? 'Installed' : 'Missing'}</StatusPill>
      </div>

      {installed && (
        <div className="mb-4 flex flex-wrap gap-4">
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
      )}

      {toolDetails.length > 0 && (
        <div className="mb-4">
          <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted">
            Tools
          </span>
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

      {installed ? (
        <Button
          variant="ghost"
          icon={isRemoving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
          className="text-cursor-semantic-error hover:bg-cursor-canvas-soft"
          disabled={isRemoving}
          onClick={() => onRemove?.(image.image)}
        >
          {isRemoving ? 'Removing...' : 'Remove Image'}
        </Button>
      ) : (
        <Button
          variant="primary"
          icon={isDownloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          disabled={isDownloading}
          onClick={() => onDownload?.(image.image)}
        >
          {isDownloading ? 'Downloading...' : 'Download Image'}
        </Button>
      )}
    </div>
  );
}

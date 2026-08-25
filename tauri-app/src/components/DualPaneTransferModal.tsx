import React, {useState, useEffect, useCallback, useMemo} from 'react';
import {
  X,
  Upload,
  Folder,
  FolderPlus,
  FolderOpen,
  File,
  HardDrive,
  Server,
  ArrowUp,
  ArrowRight,
  RefreshCw,
  Loader2,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import {open as openDialog} from '@tauri-apps/plugin-dialog';
import {useLocalBrowseMutation, useRemoteBrowseMutation, useUploadStageMutation, useRemoteMkdirMutation} from '../query/useRemote';
import {Button, Alert, inputCls} from './ui';
import type {RemoteBrowseEntry, RemoteBrowseResponse} from '../types/backend';
import type {RemotePayload} from '../api/runConfig';

function hasTauriInternals(): boolean {
  if (typeof window === 'undefined') return false;
  const internals = (window as unknown as {__TAURI_INTERNALS__?: {invoke?: unknown}}).__TAURI_INTERNALS__;
  return typeof internals?.invoke === 'function';
}

function selectedDialogPath(selected: Awaited<ReturnType<typeof openDialog>>): string {
  if (Array.isArray(selected)) return selected[0] || '';
  return selected || '';
}

function fmtBytes(bytes: number | null | undefined): string {
  if (bytes == null || isNaN(bytes)) return '-';
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

function fmtDate(timestampSec: number | null | undefined): string {
  if (!timestampSec) return '-';
  const d = new Date(timestampSec * 1000);
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getFormatBadge(entry: RemoteBrowseEntry): {label: string; isPrimary: boolean} {
  if (entry.is_dicom_series) {
    return {label: `DCM (${entry.slice_count ?? '?'} sl)`, isPrimary: true};
  }
  if (entry.kind === 'directory') {
    return {label: 'DIR', isPrimary: false};
  }
  const lower = entry.name.toLowerCase();
  if (lower.endsWith('.nii.gz') || lower.endsWith('.nii')) {
    return {label: 'NII', isPrimary: true};
  }
  if (lower.endsWith('.mgz') || lower.endsWith('.mgh')) {
    return {label: 'MGZ', isPrimary: true};
  }
  if (lower.endsWith('.dcm') || lower.endsWith('.dicom') || lower.endsWith('.ima')) {
    return {label: 'DCM', isPrimary: true};
  }
  if (entry.selectable) {
    return {label: 'IMG', isPrimary: true};
  }
  return {label: 'FILE', isPrimary: false};
}

export interface DualPaneTransferModalProps {
  onClose: () => void;
  remotePayload: RemotePayload;
  initialLocalPath?: string;
  initialRemotePath?: string;
  onSetInputLocation?: (remotePath: string) => void;
}

export function DualPaneTransferModal({
  onClose,
  remotePayload,
  initialLocalPath = '',
  initialRemotePath = '~',
  onSetInputLocation,
}: DualPaneTransferModalProps) {
  const localBrowseMutation = useLocalBrowseMutation();
  const remoteBrowseMutation = useRemoteBrowseMutation();
  const uploadStageMutation = useUploadStageMutation();
  const remoteMkdirMutation = useRemoteMkdirMutation();

  // Left Pane (Local) state
  const [leftPath, setLeftPath] = useState(initialLocalPath || '');
  const [leftManualPath, setLeftManualPath] = useState(initialLocalPath || '');
  const [leftParent, setLeftParent] = useState('');
  const [leftEntries, setLeftEntries] = useState<RemoteBrowseEntry[]>([]);
  const [leftSelected, setLeftSelected] = useState<Set<string>>(new Set());
  const [leftError, setLeftError] = useState<string | null>(null);

  // Right Pane (Remote) state
  const [rightPath, setRightPath] = useState(initialRemotePath || '~');
  const [rightManualPath, setRightManualPath] = useState(initialRemotePath || '~');
  const [rightParent, setRightParent] = useState('~');
  const [rightEntries, setRightEntries] = useState<RemoteBrowseEntry[]>([]);
  const [rightSelected, setRightSelected] = useState<string | null>(null);
  const [rightError, setRightError] = useState<string | null>(null);

  // Transfer & New Folder state
  const [transferStatus, setTransferStatus] = useState<{
    type: 'idle' | 'in_progress' | 'success' | 'error';
    message: string;
  } | null>(null);
  const [isNewFolderOpen, setIsNewFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [newFolderError, setNewFolderError] = useState<string | null>(null);

  // Browse local directory
  const browseLocal = useCallback(
    (path: string) => {
      setLeftError(null);
      localBrowseMutation.mutate(
        {path: path || '.', purpose: 'browse', recursive: false},
        {
          onSuccess: (res: RemoteBrowseResponse) => {
            if (!res.ok) {
              setLeftError(res.error || 'Failed to list local directory');
              setLeftEntries([]);
              return;
            }
            const resolvedPath = res.path ?? path;
            setLeftPath(resolvedPath);
            setLeftManualPath(resolvedPath);
            setLeftParent(res.parent ?? resolvedPath);
            setLeftEntries(res.entries ?? []);
            setLeftSelected(new Set());
          },
          onError: (err: unknown) => {
            setLeftError(err instanceof Error ? err.message : 'Local browse failed');
            setLeftEntries([]);
          },
        },
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Browse remote directory
  const browseRemote = useCallback(
    (path: string) => {
      setRightError(null);
      remoteBrowseMutation.mutate(
        {...remotePayload, path: path || '~', purpose: 'browse', recursive: false} as Parameters<typeof remoteBrowseMutation.mutate>[0],
        {
          onSuccess: (res: RemoteBrowseResponse) => {
            if (!res.ok) {
              setRightError(res.error || 'Failed to list remote directory');
              setRightEntries([]);
              return;
            }
            const resolvedPath = res.path ?? path;
            setRightPath(resolvedPath);
            setRightManualPath(resolvedPath);
            setRightParent(res.parent ?? resolvedPath);
            setRightEntries(res.entries ?? []);
            setRightSelected(null);
          },
          onError: (err: unknown) => {
            setRightError(err instanceof Error ? err.message : 'Remote browse failed');
            setRightEntries([]);
          },
        },
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [remotePayload],
  );

  // Initial browse on mount
  useEffect(() => {
    browseLocal(initialLocalPath || '');
    browseRemote(initialRemotePath || '~');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Left selection helpers
  const toggleLeftSelection = (path: string) => {
    setLeftSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleSelectAllLeft = () => {
    setLeftSelected(new Set(leftEntries.map((e) => e.path)));
  };

  const handleClearLeft = () => {
    setLeftSelected(new Set());
  };

  // Local folder picker dialog fallback
  const handleLocalBrowseDialog = async () => {
    if (!hasTauriInternals()) {
      alert('Native folder picker is only available in desktop app mode. Type or edit the path above.');
      return;
    }
    try {
      const selected = await openDialog({directory: true, multiple: false});
      const path = selectedDialogPath(selected);
      if (path) {
        setLeftManualPath(path);
        browseLocal(path);
      }
    } catch {
      // User cancelled
    }
  };

  // Upload selected local items to current remote directory
  const isUploading = uploadStageMutation.isPending;
  const handleUpload = () => {
    if (leftSelected.size === 0 || !rightPath || isUploading) return;
    const pathsToUpload = Array.from(leftSelected);
    setTransferStatus({
      type: 'in_progress',
      message: `Uploading ${pathsToUpload.length} item(s) to ${rightPath}...`,
    });

    uploadStageMutation.mutate(
      {
        ...remotePayload,
        local_paths: pathsToUpload,
        remote_path: rightPath,
      },
      {
        onSuccess: (res) => {
          if (res.ok) {
            setTransferStatus({
              type: 'success',
              message: `Successfully uploaded ${pathsToUpload.length} item(s) to ${rightPath}`,
            });
            setLeftSelected(new Set());
            // Refresh right remote pane to show uploaded items
            browseRemote(rightPath);
          } else {
            setTransferStatus({
              type: 'error',
              message: res.error || 'Upload failed',
            });
          }
        },
        onError: (err: unknown) => {
          setTransferStatus({
            type: 'error',
            message: err instanceof Error ? err.message : 'Upload failed',
          });
        },
      },
    );
  };

  // Create remote folder
  const isCreatingFolder = remoteMkdirMutation.isPending;
  const handleCreateRemoteFolder = () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) {
      setNewFolderError('Folder name is required');
      return;
    }
    if (trimmed.includes('/') || trimmed.includes('\\')) {
      setNewFolderError('Folder name cannot contain path separators');
      return;
    }
    const targetPath = `${rightPath.replace(/\/+$/, '')}/${trimmed}`;
    setNewFolderError(null);

    remoteMkdirMutation.mutate(
      {
        ...remotePayload,
        path: targetPath,
      },
      {
        onSuccess: (res) => {
          if (res.ok) {
            setIsNewFolderOpen(false);
            setNewFolderName('');
            setTransferStatus({
              type: 'success',
              message: `Created remote folder "${trimmed}"`,
            });
            browseRemote(rightPath);
          } else {
            setNewFolderError(res.error || 'Failed to create folder');
          }
        },
        onError: (err: unknown) => {
          setNewFolderError(err instanceof Error ? err.message : 'Failed to create folder');
        },
      },
    );
  };

  // Set as pipeline input location
  const handleSetInputLocation = () => {
    const target = rightSelected || rightPath;
    if (onSetInputLocation && target) {
      onSetInputLocation(target);
      setTransferStatus({
        type: 'success',
        message: `Set "${target}" as pipeline input location.`,
      });
    }
  };

  const leftDirs = useMemo(() => leftEntries.filter((e) => e.kind === 'directory'), [leftEntries]);
  const leftFiles = useMemo(() => leftEntries.filter((e) => e.kind === 'file'), [leftEntries]);
  const rightDirs = useMemo(() => rightEntries.filter((e) => e.kind === 'directory'), [rightEntries]);
  const rightFiles = useMemo(() => rightEntries.filter((e) => e.kind === 'file'), [rightEntries]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/40 backdrop-blur-xs p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !isUploading) onClose();
      }}
    >
      <div
        className="flex flex-col bg-cursor-surface-card border border-cursor-hairline rounded-xl shadow-2xl w-full max-w-[94vw] h-[90vh] overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-cursor-hairline px-4 py-3 bg-cursor-canvas-soft flex-none">
          <div className="flex items-center gap-2">
            <Upload className="h-4 w-4 text-cursor-primary" />
            <h2 id="modal-title" className="text-base font-semibold text-cursor-ink m-0">
              Upload Data to Server
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isUploading}
            aria-label="Close modal"
            className="rounded-md p-1 text-cursor-muted hover:bg-cursor-surface-card hover:text-cursor-ink transition-colors disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Dual-Pane Body */}
        <div className="grid grid-cols-[1fr_auto_1fr] flex-1 min-h-0 divide-x divide-cursor-hairline">
          {/* Left Pane (Local Computer) */}
          <div className="flex flex-col min-w-0 h-full bg-cursor-surface-card">
            {/* Left Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-cursor-hairline-soft bg-cursor-canvas-soft/50">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-cursor-ink">
                <HardDrive className="h-3.5 w-3.5 text-cursor-primary" />
                <span>Local Computer</span>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  className="h-6 px-2 text-2xs"
                  onClick={handleSelectAllLeft}
                  disabled={leftEntries.length === 0 || localBrowseMutation.isPending}
                >
                  Select All
                </Button>
                <Button
                  variant="ghost"
                  className="h-6 px-2 text-2xs"
                  onClick={handleClearLeft}
                  disabled={leftSelected.size === 0}
                >
                  Clear
                </Button>
                {leftSelected.size > 0 && (
                  <span className="text-2xs font-semibold text-cursor-primary bg-cursor-primary/10 px-1.5 py-0.5 rounded">
                    {leftSelected.size} selected
                  </span>
                )}
              </div>
            </div>

            {/* Left Path Bar */}
            <div className="flex items-center gap-1.5 p-2 border-b border-cursor-hairline-soft bg-cursor-canvas-soft">
              <input
                className={`${inputCls} min-w-0 flex-1 font-mono text-xs h-7.5 px-2`}
                value={leftManualPath}
                onChange={(e) => setLeftManualPath(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') browseLocal(leftManualPath);
                }}
                placeholder="/local/data/path"
                aria-label="Local path"
              />
              <button
                type="button"
                onClick={() => browseLocal(leftManualPath)}
                disabled={localBrowseMutation.isPending}
                className="inline-flex h-7.5 items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card px-2 text-xs font-medium text-cursor-ink hover:bg-cursor-canvas-soft disabled:opacity-50"
                title="Go to path"
              >
                Go
              </button>
              <button
                type="button"
                onClick={() => browseLocal(leftParent)}
                disabled={!leftParent || leftParent === leftPath || localBrowseMutation.isPending}
                className="inline-flex h-7.5 w-7.5 items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card text-cursor-ink hover:bg-cursor-canvas-soft disabled:opacity-40"
                title="Up one directory"
                aria-label="Up one directory"
              >
                <ArrowUp className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={handleLocalBrowseDialog}
                className="inline-flex h-7.5 items-center justify-center gap-1 rounded-md border border-cursor-hairline bg-cursor-surface-card px-2 text-xs font-medium text-cursor-ink hover:bg-cursor-canvas-soft"
                title="Browse folder dialog"
              >
                <FolderOpen className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => browseLocal(leftPath)}
                disabled={localBrowseMutation.isPending}
                className="inline-flex h-7.5 w-7.5 items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card text-cursor-ink hover:bg-cursor-canvas-soft disabled:opacity-50"
                title="Refresh local files"
                aria-label="Refresh local files"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${localBrowseMutation.isPending ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {/* Left File List */}
            <div className="flex-1 overflow-y-auto min-h-0 bg-cursor-surface-card divide-y divide-cursor-hairline-soft">
              {leftParent && leftParent !== leftPath && !localBrowseMutation.isPending && (
                <button
                  type="button"
                  onClick={() => browseLocal(leftParent)}
                  className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-xs text-cursor-primary hover:bg-cursor-canvas-soft transition-colors"
                >
                  <span className="w-4 h-4 flex items-center justify-center">
                    <ArrowUp className="h-3.5 w-3.5 text-cursor-muted" />
                  </span>
                  <span className="font-mono text-cursor-muted">..</span>
                </button>
              )}

              {localBrowseMutation.isPending && (
                <div className="flex items-center justify-center py-12 text-xs text-cursor-muted gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Loading local files...</span>
                </div>
              )}

              {!localBrowseMutation.isPending && leftError && (
                <div className="p-3">
                  <Alert severity="error" size="sm">
                    {leftError}
                  </Alert>
                </div>
              )}

              {!localBrowseMutation.isPending && !leftError && leftEntries.length === 0 && (
                <div className="flex items-center justify-center py-12 text-xs text-cursor-muted">
                  Directory is empty.
                </div>
              )}

              {!localBrowseMutation.isPending && !leftError && (
                <>
                  {/* Directories */}
                  {leftDirs.map((entry) => {
                    const isSelected = leftSelected.has(entry.path);
                    const badge = getFormatBadge(entry);
                    return (
                      <div
                        key={entry.path}
                        className={`flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-cursor-canvas-soft cursor-pointer select-none transition-colors ${
                          isSelected ? 'bg-cursor-primary/5' : ''
                        }`}
                        onClick={() => toggleLeftSelection(entry.path)}
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          browseLocal(entry.path);
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleLeftSelection(entry.path)}
                          onClick={(e) => e.stopPropagation()}
                          className="h-3.5 w-3.5 flex-none accent-cursor-primary"
                          aria-label={`Select ${entry.name}`}
                        />
                        <Folder className="h-4 w-4 flex-none text-cursor-primary/80" />
                        <span
                          className={`inline-flex h-4 px-1.5 flex-none items-center justify-center rounded text-2xs font-semibold uppercase tracking-wide ${
                            badge.isPrimary
                              ? 'bg-cursor-primary/10 text-cursor-primary'
                              : 'bg-cursor-canvas text-cursor-muted'
                          }`}
                        >
                          {badge.label}
                        </span>
                        <span className="min-w-0 flex-1 truncate font-medium text-cursor-ink" title={entry.name}>
                          {entry.name}
                        </span>
                        {entry.size != null && (
                          <span className="flex-none text-right text-cursor-muted text-2xs" style={{minWidth: '3.5rem'}}>
                            {fmtBytes(entry.size)}
                          </span>
                        )}
                        <span className="flex-none text-right text-cursor-muted text-2xs" style={{minWidth: '5.5rem'}}>
                          {fmtDate(entry.modified_at)}
                        </span>
                      </div>
                    );
                  })}

                  {/* Files */}
                  {leftFiles.map((entry) => {
                    const isSelected = leftSelected.has(entry.path);
                    const badge = getFormatBadge(entry);
                    return (
                      <div
                        key={entry.path}
                        className={`flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-cursor-canvas-soft cursor-pointer select-none transition-colors ${
                          isSelected ? 'bg-cursor-primary/5' : ''
                        }`}
                        onClick={() => toggleLeftSelection(entry.path)}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleLeftSelection(entry.path)}
                          onClick={(e) => e.stopPropagation()}
                          className="h-3.5 w-3.5 flex-none accent-cursor-primary"
                          aria-label={`Select ${entry.name}`}
                        />
                        <File className="h-4 w-4 flex-none text-cursor-muted" />
                        <span
                          className={`inline-flex h-4 px-1.5 flex-none items-center justify-center rounded text-2xs font-semibold uppercase tracking-wide ${
                            badge.isPrimary
                              ? 'bg-cursor-primary/10 text-cursor-primary'
                              : 'bg-cursor-canvas text-cursor-muted'
                          }`}
                        >
                          {badge.label}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-cursor-body" title={entry.name}>
                          {entry.name}
                        </span>
                        <span className="flex-none text-right text-cursor-muted text-2xs" style={{minWidth: '3.5rem'}}>
                          {fmtBytes(entry.size)}
                        </span>
                        <span className="flex-none text-right text-cursor-muted text-2xs" style={{minWidth: '5.5rem'}}>
                          {fmtDate(entry.modified_at)}
                        </span>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          </div>

          {/* Center Transfer Action Column */}
          <div className="flex flex-col items-center justify-center px-3 py-6 bg-cursor-canvas-soft gap-4 flex-none">
            <button
              type="button"
              onClick={handleUpload}
              disabled={leftSelected.size === 0 || isUploading}
              className="inline-flex flex-col items-center justify-center gap-1.5 rounded-lg border border-cursor-primary bg-cursor-primary text-white px-3 py-2.5 text-xs font-semibold shadow-xs hover:bg-cursor-primary-active transition-colors disabled:cursor-not-allowed disabled:opacity-40"
              title={leftSelected.size > 0 ? `Upload ${leftSelected.size} item(s) to remote directory` : 'Select local items to upload'}
            >
              {isUploading ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <ArrowRight className="h-5 w-5" />
              )}
              <span>Upload -&gt;</span>
            </button>
          </div>

          {/* Right Pane (Remote Server) */}
          <div className="flex flex-col min-w-0 h-full bg-cursor-surface-card">
            {/* Right Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-cursor-hairline-soft bg-cursor-canvas-soft/50">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-cursor-ink">
                <Server className="h-3.5 w-3.5 text-cursor-primary" />
                <span>Remote Server (SSH)</span>
              </div>
              <div className="flex items-center gap-1">
                {onSetInputLocation && (
                  <Button
                    variant="base"
                    className="h-6 px-2 text-2xs font-semibold text-cursor-primary"
                    onClick={handleSetInputLocation}
                    title="Apply current remote path to pipeline input"
                  >
                    Set as Input Location
                  </Button>
                )}
              </div>
            </div>

            {/* Right Path Bar */}
            <div className="flex items-center gap-1.5 p-2 border-b border-cursor-hairline-soft bg-cursor-canvas-soft">
              <input
                className={`${inputCls} min-w-0 flex-1 font-mono text-xs h-7.5 px-2`}
                value={rightManualPath}
                onChange={(e) => setRightManualPath(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') browseRemote(rightManualPath);
                }}
                placeholder="~/mri-uploads"
                aria-label="Remote path"
              />
              <button
                type="button"
                onClick={() => browseRemote(rightManualPath)}
                disabled={remoteBrowseMutation.isPending}
                className="inline-flex h-7.5 items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card px-2 text-xs font-medium text-cursor-ink hover:bg-cursor-canvas-soft disabled:opacity-50"
                title="Go to path"
              >
                Go
              </button>
              <button
                type="button"
                onClick={() => browseRemote(rightParent)}
                disabled={!rightParent || rightParent === rightPath || remoteBrowseMutation.isPending}
                className="inline-flex h-7.5 w-7.5 items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card text-cursor-ink hover:bg-cursor-canvas-soft disabled:opacity-40"
                title="Up one directory"
                aria-label="Up one directory"
              >
                <ArrowUp className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setNewFolderName('');
                  setNewFolderError(null);
                  setIsNewFolderOpen(true);
                }}
                className="inline-flex h-7.5 items-center justify-center gap-1 rounded-md border border-cursor-hairline bg-cursor-surface-card px-2 text-xs font-medium text-cursor-ink hover:bg-cursor-canvas-soft"
                title="Create new remote folder"
              >
                <FolderPlus className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">New Folder</span>
              </button>
              <button
                type="button"
                onClick={() => browseRemote(rightPath)}
                disabled={remoteBrowseMutation.isPending}
                className="inline-flex h-7.5 w-7.5 items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card text-cursor-ink hover:bg-cursor-canvas-soft disabled:opacity-50"
                title="Refresh remote files"
                aria-label="Refresh remote files"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${remoteBrowseMutation.isPending ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {/* Right File List */}
            <div className="flex-1 overflow-y-auto min-h-0 bg-cursor-surface-card divide-y divide-cursor-hairline-soft">
              {rightParent && rightParent !== rightPath && !remoteBrowseMutation.isPending && (
                <button
                  type="button"
                  onClick={() => browseRemote(rightParent)}
                  className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-xs text-cursor-primary hover:bg-cursor-canvas-soft transition-colors"
                >
                  <span className="w-4 h-4 flex items-center justify-center">
                    <ArrowUp className="h-3.5 w-3.5 text-cursor-muted" />
                  </span>
                  <span className="font-mono text-cursor-muted">..</span>
                </button>
              )}

              {remoteBrowseMutation.isPending && (
                <div className="flex items-center justify-center py-12 text-xs text-cursor-muted gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Loading remote files...</span>
                </div>
              )}

              {!remoteBrowseMutation.isPending && rightError && (
                <div className="p-3">
                  <Alert severity="error" size="sm">
                    {rightError}
                  </Alert>
                </div>
              )}

              {!remoteBrowseMutation.isPending && !rightError && rightEntries.length === 0 && (
                <div className="flex items-center justify-center py-12 text-xs text-cursor-muted">
                  Directory is empty.
                </div>
              )}

              {!remoteBrowseMutation.isPending && !rightError && (
                <>
                  {/* Directories */}
                  {rightDirs.map((entry) => {
                    const isSelected = rightSelected === entry.path;
                    const badge = getFormatBadge(entry);
                    return (
                      <div
                        key={entry.path}
                        className={`flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-cursor-canvas-soft cursor-pointer select-none transition-colors ${
                          isSelected ? 'bg-cursor-primary/10' : ''
                        }`}
                        onClick={() => setRightSelected(entry.path)}
                        onDoubleClick={() => browseRemote(entry.path)}
                      >
                        <Folder className="h-4 w-4 flex-none text-cursor-primary/80" />
                        <span
                          className={`inline-flex h-4 px-1.5 flex-none items-center justify-center rounded text-2xs font-semibold uppercase tracking-wide ${
                            badge.isPrimary
                              ? 'bg-cursor-primary/10 text-cursor-primary'
                              : 'bg-cursor-canvas text-cursor-muted'
                          }`}
                        >
                          {badge.label}
                        </span>
                        <span className="min-w-0 flex-1 truncate font-medium text-cursor-ink" title={entry.name}>
                          {entry.name}
                        </span>
                        {entry.size != null && (
                          <span className="flex-none text-right text-cursor-muted text-2xs" style={{minWidth: '3.5rem'}}>
                            {fmtBytes(entry.size)}
                          </span>
                        )}
                        <span className="flex-none text-right text-cursor-muted text-2xs" style={{minWidth: '5.5rem'}}>
                          {fmtDate(entry.modified_at)}
                        </span>
                      </div>
                    );
                  })}

                  {/* Files */}
                  {rightFiles.map((entry) => {
                    const isSelected = rightSelected === entry.path;
                    const badge = getFormatBadge(entry);
                    return (
                      <div
                        key={entry.path}
                        className={`flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-cursor-canvas-soft cursor-pointer select-none transition-colors ${
                          isSelected ? 'bg-cursor-primary/10' : ''
                        }`}
                        onClick={() => setRightSelected(entry.path)}
                      >
                        <File className="h-4 w-4 flex-none text-cursor-muted" />
                        <span
                          className={`inline-flex h-4 px-1.5 flex-none items-center justify-center rounded text-2xs font-semibold uppercase tracking-wide ${
                            badge.isPrimary
                              ? 'bg-cursor-primary/10 text-cursor-primary'
                              : 'bg-cursor-canvas text-cursor-muted'
                          }`}
                        >
                          {badge.label}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-cursor-body" title={entry.name}>
                          {entry.name}
                        </span>
                        <span className="flex-none text-right text-cursor-muted text-2xs" style={{minWidth: '3.5rem'}}>
                          {fmtBytes(entry.size)}
                        </span>
                        <span className="flex-none text-right text-cursor-muted text-2xs" style={{minWidth: '5.5rem'}}>
                          {fmtDate(entry.modified_at)}
                        </span>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Footer / Status Bar */}
        <div className="flex items-center justify-between border-t border-cursor-hairline px-4 py-2.5 bg-cursor-canvas-soft flex-none">
          <div className="flex items-center gap-2 text-xs min-w-0">
            {transferStatus?.type === 'in_progress' && (
              <>
                <Loader2 className="h-3.5 w-3.5 text-cursor-primary animate-spin flex-none" />
                <span className="text-cursor-primary truncate font-medium">{transferStatus.message}</span>
              </>
            )}
            {transferStatus?.type === 'success' && (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-cursor-semantic-success flex-none" />
                <span className="text-cursor-semantic-success truncate font-medium">{transferStatus.message}</span>
              </>
            )}
            {transferStatus?.type === 'error' && (
              <>
                <AlertCircle className="h-3.5 w-3.5 text-cursor-semantic-error flex-none" />
                <span className="text-cursor-semantic-error truncate font-medium">{transferStatus.message}</span>
              </>
            )}
            {!transferStatus && (
              <span className="text-cursor-muted truncate">
                Select items on the left and click &quot;Upload -&gt;&quot; to transfer files to server.
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-none">
            <Button variant="ghost" onClick={onClose} disabled={isUploading}>
              Close
            </Button>
          </div>
        </div>
      </div>

      {/* New Folder Modal */}
      {isNewFolderOpen && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-cursor-ink/40 p-4"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !isCreatingFolder) setIsNewFolderOpen(false);
          }}
        >
          <div className="rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 max-w-sm w-full shadow-lg">
            <h3 className="m-0 mb-2 text-sm font-semibold text-cursor-ink">Create Remote Folder</h3>
            <p className="text-xs text-cursor-muted mb-3">
              Create a new directory inside <span className="font-mono text-cursor-ink">{rightPath}</span>
            </p>
            <input
              className={`${inputCls} w-full text-xs mb-2`}
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateRemoteFolder();
                if (e.key === 'Escape') setIsNewFolderOpen(false);
              }}
              placeholder="folder_name"
              autoFocus
              aria-label="New folder name"
            />
            {newFolderError && (
              <div className="mb-2">
                <Alert severity="error" size="sm">
                  {newFolderError}
                </Alert>
              </div>
            )}
            <div className="flex justify-end gap-2 mt-3">
              <Button variant="ghost" onClick={() => setIsNewFolderOpen(false)} disabled={isCreatingFolder}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleCreateRemoteFolder}
                disabled={!newFolderName.trim() || isCreatingFolder}
                icon={isCreatingFolder ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : undefined}
              >
                {isCreatingFolder ? 'Creating...' : 'Create'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

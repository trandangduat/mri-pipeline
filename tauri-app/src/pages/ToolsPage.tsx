import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Container, Download, Loader2, RefreshCw, CheckCircle2, XCircle, Cpu, AlertCircle} from 'lucide-react';
import {Button, StatusPill} from '../components/ui';
import {InstalledImageCard, MissingImageCard} from '../components/ImageCard';
import {ConfirmDialog} from '../components/ConfirmDialog';
import {isImageInstalled, isImageDownloading} from '../lib/tools';
import type {ToolImage} from '../types/backend';
import {useEnvironment} from '../query/useEnvironment';
import {useLocalImageStatusMutation, useRemoveImage, usePullImageStream} from '../query/useTools';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useToolsStore} from '../stores/toolsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUiStore} from '../stores/uiStore';
import {buildRemotePayload} from '../api/runConfig';

const POLL_INTERVAL_MS = 5000;
const GRID_CLASSES = 'grid gap-4.5 [grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]';

export function ToolsPage() {
  const {data: environment, refetch: refetchEnvironment} = useEnvironment();

  const formValues = usePipelineFormStore((s) => s.formValues);
  const remoteResult = useRemoteStore();

  const cachedImagesByKey = useToolsStore((s) => s.cachedImagesByKey);
  const latestImages = useToolsStore((s) => s.latestImages);
  const setLatestImages = useToolsStore((s) => s.setLatestImages);

  const busy = useUiStore((s) => s.busy);
  const setBusyKey = useUiStore((s) => s.setBusyKey);

  const removeImageMutation = useRemoveImage();
  const pullStream = usePullImageStream();
  const localImageStatusMutation = useLocalImageStatusMutation();

  const [removingImage, setRemovingImage] = useState<string | null>(null);
  const [imageToRemove, setImageToRemove] = useState<string | null>(null);

  const selectedRuntimeTarget = () => (formValues.runtimeTarget === 'Server' ? 'Server' : 'Local');

  const python = ((environment as Record<string, unknown> | undefined)?.python as
    {ok?: boolean; path?: string; version?: string} | undefined) || {ok: false, path: '', version: ''};
  const docker = ((environment as Record<string, unknown> | undefined)?.docker as
    {ok?: boolean; path?: string} | undefined) || {ok: false, path: ''};

  const images = (latestImages || []) as ToolImage[];
  const installedImages = images.filter(isImageInstalled);
  const missingImages = images.filter((img) => !isImageInstalled(img));
  const hasDownloading = images.some(isImageDownloading);

  const refreshTools = useCallback(async ({manual = true}: {manual?: boolean} = {}) => {
    const target = selectedRuntimeTarget();
    if (target === 'Server' && !remoteResult.connected) {
      return;
    }
    const cacheKey = target === 'Server'
      ? `Server:${remoteResult.config?.host || ''}:${remoteResult.config?.port || ''}:${remoteResult.config?.username || ''}`
      : 'Local';
    const selectedTools: Record<string, string> = {};
    setBusyKey('refreshTools', true);
    try {
      const result = await localImageStatusMutation.mutateAsync({
        selectedTools,
        options: {
          target,
          remote: target === 'Server' ? buildRemotePayload(formValues) : null,
        },
      });
      if (!result.ok) {
        return;
      }
      const imgs = Array.isArray(result.images) ? result.images : [];
      setLatestImages(imgs, cacheKey);
    } catch (error: unknown) {
      // Keep existing cached data
    } finally {
      setBusyKey('refreshTools', false);
    }
  }, [formValues, remoteResult.connected, remoteResult.config?.host, remoteResult.config?.port, remoteResult.config?.username, localImageStatusMutation, setBusyKey, setLatestImages]);

  const autoCheckKeyRef = useRef<string>('');

  useEffect(() => {
    const target = selectedRuntimeTarget();
    const key = target === 'Server'
      ? `Server:${remoteResult.config?.host || ''}:${remoteResult.config?.port || ''}:${remoteResult.config?.username || ''}`
      : 'Local';

    // Immediately restore cached images if present to avoid skeleton flicker
    const cached = cachedImagesByKey[key];
    if (cached && Array.isArray(cached) && cached.length > 0) {
      setLatestImages(cached);
    }

    if (autoCheckKeyRef.current === key) return;
    autoCheckKeyRef.current = key;

    if (target === 'Server' && !remoteResult.connected) {
      return;
    }
    void refreshTools({manual: false});
  }, [formValues.runtimeTarget, remoteResult.connected, remoteResult.config?.host, remoteResult.config?.port, remoteResult.config?.username, cachedImagesByKey, refreshTools, setLatestImages]);

  useEffect(() => {
    if (!hasDownloading) return;
    const interval = setInterval(() => {
      void refreshTools({manual: false});
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [hasDownloading, refreshTools]);

  const isRefreshing = Boolean(busy.checkEnv || busy.refreshTools);

  const refreshEnvironment = async () => {
    setBusyKey('checkEnv', true);
    try {
      await refetchEnvironment();
    } finally {
      setBusyKey('checkEnv', false);
    }
  };

  const refreshAll = async () => {
    await Promise.all([
      refreshEnvironment(),
      refreshTools({manual: true}),
    ]);
  };

  const handleRequestRemove = (image: string) => {
    setImageToRemove(image);
  };

  const handleConfirmRemove = async () => {
    if (!imageToRemove) return;
    const image = imageToRemove;
    const target = selectedRuntimeTarget();
    setRemovingImage(image);
    try {
      const result = await removeImageMutation.mutateAsync({
        image,
        target,
        remote: target === 'Server' ? buildRemotePayload(formValues) : null,
      });
      if (result.ok) {
        setImageToRemove(null);
        await refreshTools({manual: false});
      }
    } finally {
      setRemovingImage(null);
    }
  };

  const handleDownload = (image: string) => {
    const target = selectedRuntimeTarget();
    if (target === 'Server' && !remoteResult.connected) {
      return;
    }
    void pullStream.pull(image, {
      target,
      remote: target === 'Server' ? buildRemotePayload(formValues) : null,
    });
  };

  const target = selectedRuntimeTarget();

  return (
    <div className="h-full w-full overflow-y-auto p-4">
      <div className="grid gap-4">

        {/* Section 1: Environment Check */}
        <section>
          <div className="mb-2.5 flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-cursor-ink">
              <Container className="h-4 w-4 text-cursor-primary" />
              Environment Status
            </h2>
            <Button
              variant="ghost"
              icon={isRefreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              onClick={() => void refreshAll()}
              disabled={isRefreshing}
            >
              {isRefreshing ? 'Refreshing...' : 'Refresh'}
            </Button>
          </div>

          <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(14rem,1fr))]">
            <div className="flex items-center gap-2.5 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-cursor-primary/10">
                <Cpu className="h-4 w-4 text-cursor-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <span className="block text-2xs font-semibold uppercase tracking-[0.08em] text-cursor-muted">Runtime Target</span>
                <span className="inline-flex rounded border border-cursor-hairline-soft bg-cursor-canvas-soft px-1.5 py-0.25 text-xs font-semibold text-cursor-ink font-mono">
                  {target}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2.5 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-cursor-semantic-success/10">
                {python.ok ? <CheckCircle2 className="h-4 w-4 text-cursor-semantic-success" /> : <XCircle className="h-4 w-4 text-cursor-semantic-error" />}
              </div>
              <div className="min-w-0 flex-1">
                <span className="block text-2xs font-semibold uppercase tracking-[0.08em] text-cursor-muted">Python</span>
                <div className="flex items-center gap-1.5">
                  <StatusPill state={python.ok ? 'installed' : 'missing'}>
                    {python.ok ? 'Ready' : 'Missing'}
                  </StatusPill>
                  {python.ok && python.version && (
                    <code className="font-mono text-xs text-cursor-muted">{python.version}</code>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2.5 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-cursor-semantic-success/10">
                {docker.ok ? <CheckCircle2 className="h-4 w-4 text-cursor-semantic-success" /> : <XCircle className="h-4 w-4 text-cursor-semantic-error" />}
              </div>
              <div className="min-w-0 flex-1">
                <span className="block text-2xs font-semibold uppercase tracking-[0.08em] text-cursor-muted">Docker</span>
                <StatusPill state={docker.ok ? 'installed' : 'missing'}>
                  {docker.ok ? 'Ready' : 'Missing'}
                </StatusPill>
              </div>
            </div>
          </div>
        </section>

        {/* Section 2: Available Images */}
        <section>
          <div className="mb-2.5 flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-cursor-ink">
              <CheckCircle2 className="h-4 w-4 text-cursor-semantic-success" />
              Available Images ({installedImages.length})
            </h2>
          </div>

          {installedImages.length > 0 ? (
            <div className={GRID_CLASSES}>
              {installedImages.map((image) => (
                <InstalledImageCard
                  key={image.image}
                  image={image}
                  target={target}
                  onRemove={handleRequestRemove}
                  isRemoving={removingImage === image.image}
                />
              ))}
            </div>
          ) : isRefreshing && images.length === 0 ? (
            <div className="flex items-center gap-2 py-3 text-sm text-cursor-muted">
              <Loader2 className="h-4 w-4 animate-spin text-cursor-muted" />
              <span>Loading...</span>
            </div>
          ) : null}
        </section>

        {/* Section 3: Not Available Images */}
        <section>
          <div className="mb-2.5 flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-cursor-ink">
              <AlertCircle className="h-4 w-4 text-cursor-semantic-error" />
              Not Available ({missingImages.length})
            </h2>
          </div>

          {missingImages.length > 0 ? (
            <div className={GRID_CLASSES}>
              {missingImages.map((image) => (
                <MissingImageCard
                  key={image.image}
                  image={image}
                  target={target}
                  isDownloading={isImageDownloading(image)}
                  isFrontendPulling={pullStream.status === 'pulling' && pullStream.image === image.image}
                  onDownload={handleDownload}
                />
              ))}
            </div>
          ) : isRefreshing && images.length === 0 ? (
            <div className="flex items-center gap-2 py-3 text-sm text-cursor-muted">
              <Loader2 className="h-4 w-4 animate-spin text-cursor-muted" />
              <span>Loading...</span>
            </div>
          ) : null}

          {pullStream.status !== 'idle' && (pullStream.logs.length > 0 || pullStream.status === 'failed') && (
            <div className="mt-3 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-2.5">
              <div className="flex items-center gap-1.5 mb-1.5">
                <code className="font-mono text-xs text-cursor-ink">{pullStream.image}</code>
                <StatusPill state={pullStream.status === 'pulling' ? 'running' : pullStream.status === 'success' ? 'success' : 'failed'}>
                  {pullStream.status === 'pulling'
                    ? (pullStream.target === 'Server' ? 'Running in background' : 'Pulling')
                    : pullStream.status === 'success' ? 'Done' : 'Failed'}
                </StatusPill>
              </div>
              {pullStream.status === 'failed' && pullStream.error && (
                <div className="mb-1.5 flex items-start gap-1.5 rounded-md border border-cursor-semantic-error/30 bg-cursor-semantic-error/5 px-2.5 py-1.5">
                  <AlertCircle className="h-3.5 w-3.5 flex-none text-cursor-semantic-error mt-0.5" />
                  <span className="text-xs leading-relaxed text-cursor-semantic-error">{pullStream.error}</span>
                </div>
              )}
              <pre className="max-h-28 overflow-auto rounded border border-cursor-hairline-soft bg-cursor-surface-card p-1.5 font-mono text-2xs leading-relaxed text-cursor-body">
                {pullStream.logs.slice(-10).join('\n')}
              </pre>
              {(pullStream.status === 'success' || pullStream.status === 'failed') && (
                <Button variant="ghost" className="mt-1.5 h-5.5 px-2 text-2xs" onClick={pullStream.reset}>
                  Dismiss
                </Button>
              )}
            </div>
          )}
        </section>
      </div>

      {/* Remove Image Confirm Dialog */}
      <ConfirmDialog
        open={imageToRemove !== null}
        title="Remove Docker Image"
        entityName={imageToRemove ?? undefined}
        description="Are you sure you want to remove this Docker image? The image files will be deleted from the host disk and will need to be downloaded again before running pipelines that depend on it."
        confirmLabel="Remove Image"
        confirmLoadingLabel="Removing..."
        isLoading={removingImage !== null}
        onConfirm={handleConfirmRemove}
        onClose={() => {
          if (removingImage === null) setImageToRemove(null);
        }}
      />
    </div>
  );
}

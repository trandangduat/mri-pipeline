import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Container, Download, HardDrive, Loader2, RefreshCw, CheckCircle2, XCircle, Cpu, AlertCircle} from 'lucide-react';
import {Button, StatusPill} from '../components/ui';
import {Skeleton} from '@/components/ui/skeleton';
import {InstalledImageCard, MissingImageCard} from '../components/ImageCard';
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

function ImageStatusSkeletonGrid() {
  return (
    <div className={GRID_CLASSES}>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="rounded-xl border border-cursor-hairline bg-white p-4.5 min-h-[220px]">
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-lg" />
            <div className="flex-1">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="mt-1.5 h-3 w-1/3" />
            </div>
          </div>
          <Skeleton className="mt-4 h-3 w-1/2" />
          <div className="mt-3 flex gap-1.5">
            <Skeleton className="h-6 w-20 rounded-md" />
            <Skeleton className="h-6 w-24 rounded-md" />
          </div>
          <Skeleton className="mt-8 h-9 w-full rounded-lg" />
        </div>
      ))}
    </div>
  );
}

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

  const refreshEnvironment = async () => {
    setBusyKey('checkEnv', true);
    try {
      await refetchEnvironment();
    } finally {
      setBusyKey('checkEnv', false);
    }
  };

  const handleRemove = async (image: string) => {
    const target = selectedRuntimeTarget();
    setRemovingImage(image);
    try {
      const result = await removeImageMutation.mutateAsync({
        image,
        target,
        remote: target === 'Server' ? buildRemotePayload(formValues) : null,
      });
      if (result.ok) {
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

  const emptyMessage = () => {
    const target = selectedRuntimeTarget();
    if (busy.refreshTools) return 'Checking Docker image status...';
    if (target === 'Server' && !remoteResult.connected) return 'Connect SSH in Runtime to check server Docker images.';
    return 'Docker image status will load automatically.';
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
              variant="primary"
              icon={busy.checkEnv ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              onClick={refreshEnvironment}
              disabled={busy.checkEnv}
            >
              {busy.checkEnv ? 'Checking...' : 'Check Environment'}
            </Button>
          </div>

          <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(14rem,1fr))]">
            <div className="flex items-center gap-2.5 rounded-lg border border-cursor-hairline bg-white p-3">
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

            <div className="flex items-center gap-2.5 rounded-lg border border-cursor-hairline bg-white p-3">
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

            <div className="flex items-center gap-2.5 rounded-lg border border-cursor-hairline bg-white p-3">
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
              Available Images
              {installedImages.length > 0 && (
                <span className="ml-0.5 inline-flex rounded-full bg-cursor-semantic-success/10 px-2 py-0.25 text-2xs font-semibold text-cursor-semantic-success">
                  {installedImages.length}
                </span>
              )}
            </h2>
            <Button
              variant="ghost"
              icon={busy.refreshTools ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              onClick={() => void refreshTools({manual: true})}
              disabled={busy.refreshTools}
            >
              {busy.refreshTools ? 'Refreshing...' : 'Refresh'}
            </Button>
          </div>

          {installedImages.length > 0 ? (
            <div className={GRID_CLASSES}>
              {installedImages.map((image) => (
                <InstalledImageCard
                  key={image.image}
                  image={image}
                  target={target}
                  onRemove={handleRemove}
                  isRemoving={removingImage === image.image}
                />
              ))}
            </div>
          ) : busy.refreshTools && images.length === 0 ? (
            <ImageStatusSkeletonGrid />
          ) : (
            <div className="rounded-lg border border-dashed border-cursor-hairline-strong bg-cursor-canvas-soft p-5 text-center">
              <HardDrive className="mx-auto mb-1.5 h-6 w-6 text-cursor-muted" />
              <p className="text-xs text-cursor-body">
                {images.length === 0 ? emptyMessage() : 'No installed images found.'}
              </p>
            </div>
          )}
        </section>

        {/* Section 3: Not Available Images */}
        <section>
          <div className="mb-2.5 flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-cursor-ink">
              <AlertCircle className="h-4 w-4 text-cursor-semantic-error" />
              Not Available
              {missingImages.length > 0 && (
                <span className="ml-0.5 inline-flex rounded-full bg-cursor-semantic-error/10 px-2 py-0.25 text-2xs font-semibold text-cursor-semantic-error">
                  {missingImages.length}
                </span>
              )}
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
          ) : busy.refreshTools && images.length === 0 ? (
            <ImageStatusSkeletonGrid />
          ) : (
            <div className="rounded-lg border border-dashed border-cursor-hairline-strong bg-cursor-canvas-soft p-5 text-center">
              <CheckCircle2 className="mx-auto mb-1.5 h-6 w-6 text-cursor-semantic-success" />
              <p className="text-xs text-cursor-body">
                {images.length === 0 ? emptyMessage() : 'All required images are installed.'}
              </p>
            </div>
          )}

          {pullStream.status !== 'idle' && pullStream.logs.length > 0 && (
            <div className="mt-3 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-2.5">
              <div className="flex items-center gap-1.5 mb-1.5">
                <code className="font-mono text-xs text-cursor-ink">{pullStream.image}</code>
                <StatusPill state={pullStream.status === 'pulling' ? 'running' : pullStream.status === 'success' ? 'success' : 'failed'}>
                  {pullStream.status === 'pulling'
                    ? (pullStream.target === 'Server' ? 'Running in background' : 'Pulling')
                    : pullStream.status === 'success' ? 'Done' : 'Failed'}
                </StatusPill>
                {pullStream.status === 'failed' && pullStream.error && (
                  <span className="text-xs text-cursor-semantic-error">{pullStream.error}</span>
                )}
              </div>
              <pre className="max-h-28 overflow-auto rounded border border-cursor-hairline-soft bg-white p-1.5 font-mono text-2xs leading-relaxed text-cursor-body">
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
    </div>
  );
}

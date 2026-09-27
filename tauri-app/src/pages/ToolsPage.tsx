import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Container, Loader2, RefreshCw, CheckCircle2, XCircle, Cpu, AlertCircle, Server} from 'lucide-react';
import {Button, StatusPill} from '../components/ui';
import {InstalledImageCard, MissingImageCard} from '../components/ImageCard';
import {ConfirmDialog} from '../components/ConfirmDialog';
import {isImageInstalled, isImageDownloading} from '../lib/tools';
import type {EnvironmentResponse, RemoteEnvironmentResponse, ToolImage} from '../types/backend';
import {useEnvironment, useRemoteEnvironment} from '../query/useEnvironment';
import {useLocalImageStatusMutation, useRemoveImage, usePullImageStream} from '../query/useTools';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useToolsStore} from '../stores/toolsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUiStore} from '../stores/uiStore';
import {buildRemotePayload} from '../api/runConfig';

const POLL_INTERVAL_MS = 5000;
const GRID_CLASSES = 'grid gap-4.5 [grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]';

export function ToolsPage() {
  const formValues = usePipelineFormStore((s) => s.formValues);
  const isServerTarget = formValues.runtimeTarget === 'Server';
  const {
    data: environment,
    refetch: refetchEnvironment,
    isFetching: isFetchingEnvironment,
    error: environmentError,
  } = useEnvironment(!isServerTarget);
  const remoteResult = useRemoteStore();
  const remotePayload = useMemo(() => buildRemotePayload(formValues), [formValues]);
  const {
    data: serverEnvironment,
    error: serverEnvironmentError,
    isFetching: isFetchingServerEnvironment,
    refetch: refetchServerEnvironment,
  } = useRemoteEnvironment(remotePayload, isServerTarget && remoteResult.connected);

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

  const isRefreshing = Boolean(busy.checkEnv || busy.refreshTools || isFetchingServerEnvironment);

  const refreshEnvironment = async () => {
    if (isServerTarget) {
      if (!remoteResult.connected) return;
      setBusyKey('checkEnv', true);
      try {
        await refetchServerEnvironment();
      } finally {
        setBusyKey('checkEnv', false);
      }
      return;
    }
    setBusyKey('checkEnv', true);
    try {
      await refetchEnvironment();
    } finally {
      setBusyKey('checkEnv', false);
    }
  };

  const refreshAll = async () => {
    await Promise.all([refreshEnvironment(), refreshTools({manual: true})]);
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
              {target === 'Local' ? 'Local Environment' : 'Server Environment'}
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

          {target === 'Server' ? (
            remoteResult.connected ? (
              <ServerEnvironmentCards
                environment={serverEnvironment}
                error={serverEnvironmentError instanceof Error ? serverEnvironmentError.message : ''}
                pending={isFetchingServerEnvironment && !serverEnvironment}
              />
            ) : (
              <div className="rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3.5 text-sm text-cursor-body flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-amber-500 shrink-0" />
                <span>Server environment has not been inspected. Connect to the server in Runtime settings to check its prerequisites.</span>
              </div>
            )
          ) : (
            <LocalEnvironmentCards
              environment={environment}
              error={environmentError instanceof Error ? environmentError.message : ''}
              pending={isFetchingEnvironment && !environment}
            />
          )}
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

export function ServerEnvironmentCards({
  environment,
  error,
  pending,
}: {
  environment?: RemoteEnvironmentResponse | undefined;
  error: string;
  pending: boolean;
}) {
  const inspectionError = error || environment?.error || environment?.errors?.join(' ') || '';
  const server = environment?.server;
  const remoteEnvironment = environment?.environment;
  const docker = environment?.docker;
  const serverReady = Boolean(server?.ok);
  const computeReady = Boolean(server?.ok);
  const pythonReady = Boolean(remoteEnvironment?.ok);
  const dockerReady = Boolean(docker?.ok);
  const gpuSummary = server?.gpus?.length ? `GPU: ${server.gpus.map((gpu) => gpu.name).join(', ')}` : '';
  const ramText = formatRam(server?.total_ram_bytes);
  const dockerVersion = docker?.version
    ? (docker.version.startsWith('Docker') ? docker.version : `Docker ${docker.version}`)
    : 'Docker ready';

  if (pending) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {title: 'Resources', icon: 'server' as const},
          {title: 'Python', icon: 'python' as const},
          {title: 'Docker', icon: 'docker' as const},
        ].map(({title, icon}) => (
          <div
            key={title}
            className="flex flex-col justify-between rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4"
          >
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cursor-primary/10 text-cursor-primary">
                    {icon === 'server' ? <Server className="h-4 w-4" /> : icon === 'python' ? <PythonIcon className="h-4 w-4" /> : <DockerIcon className="h-3.5 w-4.5" />}
                  </div>
                  <span className="text-sm font-medium text-cursor-ink">
                    {title}
                  </span>
                </div>
                <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-cursor-primary/10 text-cursor-primary">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Checking
                </span>
              </div>
              <div className="h-5 w-36 animate-pulse rounded bg-cursor-hairline mb-2" />
              <div className="h-4 w-48 animate-pulse rounded bg-cursor-hairline/60" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Card 1: Resources */}
      <div className="flex flex-col justify-between rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 transition-all">
        <div>
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cursor-primary/10 text-cursor-primary">
                <Server className="h-4 w-4" />
              </div>
              <span className="text-sm font-medium text-cursor-ink">
                Resources
              </span>
            </div>
            <span
              role="img"
              aria-label={serverReady ? 'Ready' : 'Not Ready'}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                serverReady
                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
                  : 'bg-cursor-semantic-error/10 text-cursor-semantic-error'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${serverReady ? 'bg-cursor-semantic-success' : 'bg-cursor-semantic-error'}`} />
              {serverReady ? 'Ready' : 'Not Ready'}
            </span>
          </div>

          <div className="text-base font-semibold text-cursor-ink font-mono tracking-tight truncate" title={server?.hostname || ''}>
            {server?.hostname || inspectionError || 'Server unavailable'}
          </div>

          <div className="mt-2 space-y-1 text-xs text-cursor-muted">
            {computeReady ? (
              <>
                <div>{server?.logical_cores ?? 'Unknown'} cores · {ramText ? `${ramText} RAM` : 'RAM unknown'}</div>
                {gpuSummary ? (
                  <div className="truncate" title={gpuSummary}>{gpuSummary}</div>
                ) : (
                  <div>No GPU detected</div>
                )}
              </>
            ) : (
              <div className="text-cursor-semantic-error">{inspectionError || 'Compute details unavailable'}</div>
            )}
          </div>
        </div>
      </div>

      {/* Card 2: Python */}
      <div className="flex flex-col justify-between rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 transition-all">
        <div>
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cursor-primary/10 text-cursor-primary">
                <PythonIcon className="h-4 w-4" />
              </div>
              <span className="text-sm font-medium text-cursor-ink">
                Python
              </span>
            </div>
            <span
              role="img"
              aria-label={pythonReady ? 'Ready' : 'Not Ready'}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                pythonReady
                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
                  : 'bg-cursor-semantic-error/10 text-cursor-semantic-error'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${pythonReady ? 'bg-cursor-semantic-success' : 'bg-cursor-semantic-error'}`} />
              {pythonReady ? 'Ready' : 'Not Ready'}
            </span>
          </div>

          <div className="text-base font-semibold text-cursor-ink tracking-tight truncate">
            {pythonReady
              ? (remoteEnvironment?.python_version || environment?.python?.version || 'Python ready')
              : (inspectionError || 'Project Python unavailable')}
          </div>

          <div className="mt-2 space-y-1 text-xs text-cursor-muted">
            <div className="truncate font-mono" title={remoteEnvironment?.path || environment?.python?.path || ''}>
              {remoteEnvironment?.path || environment?.python?.path || 'Interpreter not detected'}
            </div>
            <div>
              {pythonReady
                ? (remoteEnvironment?.venv_exists ? 'Virtual environment (.venv)' : 'System interpreter')
                : 'Virtualenv missing'}
            </div>
          </div>
        </div>
      </div>

      {/* Card 3: Docker */}
      <div className="flex flex-col justify-between rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 transition-all">
        <div>
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cursor-primary/10 text-cursor-primary">
                <DockerIcon className="h-3.5 w-4.5" />
              </div>
              <span className="text-sm font-medium text-cursor-ink">
                Docker
              </span>
            </div>
            <span
              role="img"
              aria-label={dockerReady ? 'Ready' : 'Not Ready'}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                dockerReady
                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
                  : 'bg-cursor-semantic-error/10 text-cursor-semantic-error'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${dockerReady ? 'bg-cursor-semantic-success' : 'bg-cursor-semantic-error'}`} />
              {dockerReady ? 'Ready' : 'Not Ready'}
            </span>
          </div>

          <div className="text-base font-semibold text-cursor-ink tracking-tight truncate">
            {dockerReady
              ? dockerVersion
              : (docker?.error || inspectionError || 'Docker daemon is unavailable')}
          </div>

          <div className="mt-2 space-y-1 text-xs text-cursor-muted">
            {dockerReady ? (
              <div className="truncate font-mono">
                Docker daemon ready
              </div>
            ) : (
              <div className="text-cursor-semantic-error truncate" title={docker?.error || 'Docker daemon is unavailable'}>
                {docker?.error || 'Docker daemon is unavailable'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function PythonIcon({className = 'h-4 w-4'}: {className?: string}) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-label="Python" role="img">
      <path fill="currentColor" d="M12 2c-4.1 0-4 1.8-4 1.8v2h4v.6H6.3C4 6.4 2 7.8 2 12s1.8 5.6 4.3 5.6h1.5v-2.1c0-2.4 2.1-4.5 4.6-4.5h4c2.2 0 3.9-1.8 3.9-4V5.8C20.3 3.7 18.5 2 16.3 2H12Zm-2.2 2.1a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8Z" />
      <path fill="currentColor" opacity=".58" d="M12 22c4.1 0 4-1.8 4-1.8v-2h-4v-.6h5.7c2.3 0 4.3-1.4 4.3-5.6S20.2 6.4 17.7 6.4h-1.5v2.1c0 2.4-2.1 4.5-4.6 4.5h-4C5.4 13 3.7 14.8 3.7 17v1.2C3.7 20.3 5.5 22 7.7 22H12Zm2.2-2.1a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8Z" />
    </svg>
  );
}

function DockerIcon({className = 'h-3.5 w-4.5'}: {className?: string}) {
  return (
    <svg viewBox="0 0 32 24" className={className} aria-label="Docker" role="img">
      <path fill="currentColor" d="M4 10h4V6h4v4h4V6h4v4h4v4h3.3c-.5 3.5-3.3 6-7.1 6H8.6C5.5 20 3 17.5 3 14h1v-4Zm5-8h4v3H9V2Zm5 0h4v3h-4V2Zm5 0h4v3h-4V2Zm-9 9v3h3v-3h-3Zm4 0v3h3v-3h-3Zm4 0v3h3v-3h-3Zm4 0v3h3v-3h-3Z" />
      <circle cx="7" cy="15" r="1" fill="white" />
      <path fill="currentColor" d="M27.5 11.5c.8-1.2 1.2-2.5 1.2-4h1.3c0 2.1-.7 4-2 5.5l-.5-1.5Z" />
    </svg>
  );
}

function formatRam(value: number | null | undefined): string | null {
  if (!value || value <= 0) return null;
  return `${Math.round(value / (1024 ** 3))} GiB`;
}

export function LocalEnvironmentCards({
  environment,
  error,
  pending,
}: {
  environment?: EnvironmentResponse | undefined;
  error?: string;
  pending: boolean;
}) {
  const inspectionError = error || '';
  const hardware = environment?.hardware;
  const python = environment?.python;
  const docker = environment?.docker;
  const computeReady = Boolean(hardware?.hostname || hardware?.logical_cores);
  const localReady = Boolean(computeReady || environment?.ok);
  const pythonReady = Boolean(python?.ok);
  const dockerReady = Boolean(docker?.ok);
  const gpuSummary = hardware?.gpus?.length ? `GPU: ${hardware.gpus.map((gpu) => gpu.name).join(', ')}` : '';
  const isVenv = Boolean(python?.path && (python.path.includes('.venv') || python.path.includes('venv')));
  const pythonVersion = python?.version
    ? (python.version.startsWith('Python') ? python.version : `Python ${python.version}`)
    : 'Python ready';
  const ramText = formatRam(hardware?.total_ram_bytes);
  const dockerVersion = docker?.version
    ? (docker.version.startsWith('Docker') ? docker.version : `Docker ${docker.version}`)
    : 'Docker ready';

  if (pending) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {title: 'Resources', icon: 'cpu' as const},
          {title: 'Python', icon: 'python' as const},
          {title: 'Docker', icon: 'docker' as const},
        ].map(({title, icon}) => (
          <div
            key={title}
            className="flex flex-col justify-between rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4"
          >
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cursor-primary/10 text-cursor-primary">
                    {icon === 'cpu' ? <Cpu className="h-4 w-4" /> : icon === 'python' ? <PythonIcon className="h-4 w-4" /> : <DockerIcon className="h-3.5 w-4.5" />}
                  </div>
                  <span className="text-sm font-medium text-cursor-ink">
                    {title}
                  </span>
                </div>
                <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-cursor-primary/10 text-cursor-primary">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Checking
                </span>
              </div>
              <div className="h-5 w-36 animate-pulse rounded bg-cursor-hairline mb-2" />
              <div className="h-4 w-48 animate-pulse rounded bg-cursor-hairline/60" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Card 1: Resources */}
      <div className="flex flex-col justify-between rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 transition-all">
        <div>
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cursor-primary/10 text-cursor-primary">
                <Cpu className="h-4 w-4" />
              </div>
              <span className="text-sm font-medium text-cursor-ink">
                Resources
              </span>
            </div>
            <span
              role="img"
              aria-label={localReady ? 'Ready' : 'Not Ready'}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                localReady
                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
                  : 'bg-cursor-semantic-error/10 text-cursor-semantic-error'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${localReady ? 'bg-cursor-semantic-success' : 'bg-cursor-semantic-error'}`} />
              {localReady ? 'Ready' : 'Not Ready'}
            </span>
          </div>

          <div className="text-base font-semibold text-cursor-ink font-mono tracking-tight truncate" title={hardware?.hostname || 'localhost'}>
            {hardware?.hostname || 'localhost'}
          </div>

          <div className="mt-2 space-y-1 text-xs text-cursor-muted">
            {computeReady ? (
              <>
                <div>{hardware?.logical_cores ?? 'Unknown'} cores · {ramText ? `${ramText} RAM` : 'RAM unknown'}</div>
                {gpuSummary ? (
                  <div className="truncate" title={gpuSummary}>{gpuSummary}</div>
                ) : (
                  <div>No GPU detected</div>
                )}
              </>
            ) : (
              <div className="text-cursor-semantic-error">{inspectionError || 'Compute details unavailable'}</div>
            )}
          </div>
        </div>
      </div>

      {/* Card 2: Python */}
      <div className="flex flex-col justify-between rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 transition-all">
        <div>
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cursor-primary/10 text-cursor-primary">
                <PythonIcon className="h-4 w-4" />
              </div>
              <span className="text-sm font-medium text-cursor-ink">
                Python
              </span>
            </div>
            <span
              role="img"
              aria-label={pythonReady ? 'Ready' : 'Not Ready'}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                pythonReady
                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
                  : 'bg-cursor-semantic-error/10 text-cursor-semantic-error'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${pythonReady ? 'bg-cursor-semantic-success' : 'bg-cursor-semantic-error'}`} />
              {pythonReady ? 'Ready' : 'Not Ready'}
            </span>
          </div>

          <div className="text-base font-semibold text-cursor-ink tracking-tight truncate">
            {pythonReady ? pythonVersion : (inspectionError || 'Python unavailable')}
          </div>

          <div className="mt-2 space-y-1 text-xs text-cursor-muted">
            <div className="truncate font-mono" title={python?.path || ''}>
              {python?.path || 'Interpreter not detected'}
            </div>
            <div>
              {pythonReady
                ? (isVenv ? 'Virtual environment (.venv)' : 'System interpreter')
                : 'Python interpreter missing'}
            </div>
          </div>
        </div>
      </div>

      {/* Card 3: Docker */}
      <div className="flex flex-col justify-between rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 transition-all">
        <div>
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-cursor-primary/10 text-cursor-primary">
                <DockerIcon className="h-3.5 w-4.5" />
              </div>
              <span className="text-sm font-medium text-cursor-ink">
                Docker
              </span>
            </div>
            <span
              role="img"
              aria-label={dockerReady ? 'Ready' : 'Not Ready'}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                dockerReady
                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
                  : 'bg-cursor-semantic-error/10 text-cursor-semantic-error'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${dockerReady ? 'bg-cursor-semantic-success' : 'bg-cursor-semantic-error'}`} />
              {dockerReady ? 'Ready' : 'Not Ready'}
            </span>
          </div>

          <div className="text-base font-semibold text-cursor-ink tracking-tight truncate">
            {dockerReady ? dockerVersion : 'Docker unavailable'}
          </div>

          <div className="mt-2 space-y-1 text-xs text-cursor-muted">
            {dockerReady ? (
              <div className="truncate font-mono" title={docker?.path || ''}>
                {docker?.path || 'Docker executable detected'}
              </div>
            ) : (
              <div className="text-cursor-semantic-error truncate">
                Docker daemon is stopped or not responding
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

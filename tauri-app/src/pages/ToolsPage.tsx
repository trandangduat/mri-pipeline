import React, {useState} from 'react';
import {Container, Download, HardDrive, Loader2, RefreshCw, CheckCircle2, XCircle, Cpu} from 'lucide-react';
import {Button, StatusPill} from '../components/ui';
import {ImageCard} from '../components/ImageCard';
import {DownloadProgress} from '../components/DownloadProgress';
import {isImageInstalled} from '../lib/tools';
import type {ToolImage} from '../types/backend';
import {useEnvironment, useMetadata} from '../query/useEnvironment';
import {useLocalImageStatusMutation, useRemoveImage, usePullImageStream} from '../query/useTools';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useToolsStore} from '../stores/toolsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUiStore} from '../stores/uiStore';
import {buildRemotePayload} from '../api/runConfig';

export function ToolsPage() {
  const {data: environment, refetch: refetchEnvironment} = useEnvironment();
  const {data: metadata} = useMetadata();

  const formValues = usePipelineFormStore((s) => s.formValues);
  const remoteResult = useRemoteStore();

  const latestImages = useToolsStore((s) => s.latestImages);
  const setLatestImages = useToolsStore((s) => s.setLatestImages);

  const busy = useUiStore((s) => s.busy);
  const setBusyKey = useUiStore((s) => s.setBusyKey);

  const removeImageMutation = useRemoveImage();
  const pullStream = usePullImageStream();
  const localImageStatusMutation = useLocalImageStatusMutation();

  const [removingImage, setRemovingImage] = useState<string | null>(null);
  const [refreshMessage, setRefreshMessage] = useState<string>('');

  const selectedRuntimeTarget = () => (formValues.runtimeTarget === 'Server' ? 'Server' : 'Local');

  const python = ((environment as Record<string, unknown> | undefined)?.python as
    {ok?: boolean; path?: string; version?: string} | undefined) || {ok: false, path: '', version: ''};
  const docker = ((environment as Record<string, unknown> | undefined)?.docker as
    {ok?: boolean; path?: string} | undefined) || {ok: false, path: ''};

  const images = (latestImages || []) as ToolImage[];
  const installedImages = images.filter(isImageInstalled);
  const missingImages = images.filter((img) => !isImageInstalled(img));

  const refreshTools = async () => {
    const target = selectedRuntimeTarget();
    if (target === 'Server' && !remoteResult.connected) {
      setRefreshMessage('Connect SSH before checking server Docker images.');
      return;
    }
    let selectedTools: Record<string, string> = {};
    if (formValues.pipelineMode === 'Custom') {
      for (const stage of metadata?.stage_order || []) {
        const val = (formValues as Record<string, unknown>)[`stage_${stage}`] as string | undefined;
        if (val) selectedTools[stage] = val;
      }
    } else {
      selectedTools = metadata?.presets?.[formValues.pipelineMode]?.tools || {};
    }
    setRefreshMessage(`Checking ${target} Docker images...`);
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
        setRefreshMessage(result.error || `${target} Docker image check failed.`);
        setLatestImages([]);
        return;
      }
      const imgs = Array.isArray(result.images) ? result.images : [];
      setLatestImages(imgs);
      setRefreshMessage(`Found ${imgs.length} images — ${imgs.filter(isImageInstalled).length} installed, ${imgs.filter((i) => !isImageInstalled(i)).length} missing.`);
    } catch (error: unknown) {
      setRefreshMessage(`${target} Docker check failed: ${(error as Error).message || 'unknown error'}`);
      setLatestImages([]);
    } finally {
      setBusyKey('refreshTools', false);
    }
  };

  const refreshEnvironment = async () => {
    setBusyKey('checkEnv', true);
    try {
      await refetchEnvironment();
    } finally {
      setBusyKey('checkEnv', false);
    }
  };

  const handleRemove = async (image: string) => {
    setRemovingImage(image);
    try {
      const result = await removeImageMutation.mutateAsync(image);
      if (result.ok) {
        await refreshTools();
      }
    } finally {
      setRemovingImage(null);
    }
  };

  const handleDownload = (image: string) => {
    pullStream.pull(image);
  };

  return (
    <div className="h-full overflow-y-auto pr-2 pb-8">
      <div className="grid gap-8">

        {/* Section 1: Environment Check */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-[18px] font-semibold leading-[1.4] text-cursor-ink">
              <Container className="h-5 w-5 text-cursor-primary" />
              Environment
            </h2>
            <Button
              variant="primary"
              icon={busy.checkEnv ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              onClick={refreshEnvironment}
              disabled={busy.checkEnv}
            >
              {busy.checkEnv ? 'Checking...' : 'Check Environment'}
            </Button>
          </div>

          <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(16rem,1fr))]">
            <div className="flex items-center gap-3 rounded-xl border border-cursor-hairline bg-white p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cursor-timeline-read">
                <Cpu className="h-5 w-5 text-cursor-ink" />
              </div>
              <div className="min-w-0 flex-1">
                <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted">Runtime Target</span>
                <span className="inline-flex rounded-full border border-cursor-hairline bg-cursor-hairline-soft px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-ink">
                  {selectedRuntimeTarget()}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3 rounded-xl border border-cursor-hairline bg-white p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cursor-timeline-grep">
                {python.ok ? <CheckCircle2 className="h-5 w-5 text-cursor-ink" /> : <XCircle className="h-5 w-5 text-cursor-ink" />}
              </div>
              <div className="min-w-0 flex-1">
                <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted">Python</span>
                <div className="flex items-center gap-2">
                  <StatusPill state={python.ok ? 'installed' : 'missing'}>
                    {python.ok ? `Ready` : 'Missing'}
                  </StatusPill>
                  {python.ok && python.version && (
                    <code className="font-mono text-xs text-cursor-muted">{python.version}</code>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3 rounded-xl border border-cursor-hairline bg-white p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cursor-timeline-edit">
                {docker.ok ? <CheckCircle2 className="h-5 w-5 text-cursor-ink" /> : <XCircle className="h-5 w-5 text-cursor-ink" />}
              </div>
              <div className="min-w-0 flex-1">
                <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted">Docker</span>
                <StatusPill state={docker.ok ? 'installed' : 'missing'}>
                  {docker.ok ? 'Ready' : 'Missing'}
                </StatusPill>
              </div>
            </div>
          </div>
        </section>

        {/* Section 2: Available Images */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-[18px] font-semibold leading-[1.4] text-cursor-ink">
              <CheckCircle2 className="h-5 w-5 text-cursor-semantic-success" />
              Available Images
              {installedImages.length > 0 && (
                <span className="ml-1 inline-flex rounded-full bg-cursor-semantic-success/10 px-2.5 py-0.5 text-[11px] font-semibold text-cursor-semantic-success">
                  {installedImages.length}
                </span>
              )}
            </h2>
            <Button
              variant="ghost"
              icon={busy.refreshTools ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              onClick={refreshTools}
              disabled={busy.refreshTools}
            >
              {busy.refreshTools ? 'Refreshing...' : 'Refresh'}
            </Button>
          </div>

          {refreshMessage && (
            <div className="mb-4 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3 text-xs text-cursor-body">
              {refreshMessage}
            </div>
          )}

          {installedImages.length > 0 ? (
            <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]">
              {installedImages.map((image) => (
                <ImageCard
                  key={image.image}
                  image={image}
                  onRemove={handleRemove}
                  isRemoving={removingImage === image.image}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-cursor-hairline-strong bg-cursor-canvas-soft p-8 text-center">
              <HardDrive className="mx-auto mb-2 h-8 w-8 text-cursor-muted" />
              <p className="text-sm text-cursor-body">
                {latestImages.length === 0
                  ? 'Click "Refresh" to check Docker image status.'
                  : 'No installed images found.'}
              </p>
            </div>
          )}
        </section>

        {/* Section 3: Not Available Images */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-[18px] font-semibold leading-[1.4] text-cursor-ink">
              <Download className="h-5 w-5 text-cursor-muted" />
              Not Available
              {missingImages.length > 0 && (
                <span className="ml-1 inline-flex rounded-full bg-cursor-muted/10 px-2.5 py-0.5 text-[11px] font-semibold text-cursor-muted">
                  {missingImages.length}
                </span>
              )}
            </h2>
          </div>

          {missingImages.length > 0 ? (
            <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]">
              {missingImages.map((image) => (
                <ImageCard
                  key={image.image}
                  image={image}
                  onDownload={handleDownload}
                  isDownloading={pullStream.status === 'pulling' && pullStream.logs.length > 0}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-cursor-hairline-strong bg-cursor-canvas-soft p-8 text-center">
              <CheckCircle2 className="mx-auto mb-2 h-8 w-8 text-cursor-semantic-success" />
              <p className="text-sm text-cursor-body">
                {latestImages.length === 0
                  ? 'Click "Refresh" to check Docker image status.'
                  : 'All required images are installed.'}
              </p>
            </div>
          )}

          {/* Download Progress */}
          {pullStream.status !== 'idle' && (
            <div className="mt-4">
              <DownloadProgress
                image="docker-pull"
                state={{status: pullStream.status, logs: pullStream.logs, error: pullStream.error}}
                onClear={pullStream.reset}
              />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

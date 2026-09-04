import React, {useState} from 'react';
import {Loader2, RefreshCw} from 'lucide-react';
import {useRemoteStore} from '../stores/remoteStore';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {probeConnectionHealth} from '../lib/connectionProbe';
import {getConnectionWarningKind} from '../lib/connection';

/**
 * Slim persistent connection warning rendered above the footer on every page.
 * Short text + Retry only (no SSH settings button). Returns null while all
 * channels are healthy. The SSH warning only applies when the Server runtime
 * is in use — switching Runtime target back to Local clears it (see
 * RuntimeSection) and this guard hides any remnant.
 */
export function ConnectionStatusLine({onRetry}: {onRetry?: () => void | Promise<void>}) {
  const backendStatus = useRemoteStore((s) => s.backendStatus);
  const sshStatus = useRemoteStore((s) => s.sshStatus);
  const connected = useRemoteStore((s) => s.connected);
  const sshLastSeenAt = useRemoteStore((s) => s.sshLastSeenAt);
  const runtimeTarget = usePipelineFormStore((s) => s.formValues.runtimeTarget);
  const remoteConfig = useRemoteStore((s) => s.config);
  const formHost = usePipelineFormStore((s) => s.formValues.host);
  const formPort = usePipelineFormStore((s) => s.formValues.port);
  const formUsername = usePipelineFormStore((s) => s.formValues.username);
  const [retrying, setRetrying] = useState(false);

  const warningKind = getConnectionWarningKind({
    backendStatus,
    sshStatus,
    connected,
    sshLastSeenAt,
    runtimeTarget,
  });
  const backendDown = warningKind === 'backend';
  if (warningKind === null) return null;

  const serverLabel = remoteConfig
    ? `${remoteConfig.username}@${remoteConfig.host}:${remoteConfig.port}`
    : formHost
      ? `${formUsername}@${formHost}:${formPort}`
      : 'the server';

  const handleRetry = async () => {
    if (retrying) return;
    if (onRetry) {
      await onRetry();
      return;
    }
    setRetrying(true);
    try {
      await probeConnectionHealth();
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div
      role="alert"
      className={`flex w-full flex-none items-center justify-center gap-3 border-l-4 px-4 py-1.5 text-xs font-medium ${
        backendDown
          ? 'border-rose-700 bg-rose-500/15 text-rose-950 dark:border-rose-600 dark:bg-rose-500/20 dark:text-rose-100'
          : 'border-amber-700 bg-amber-500/15 text-amber-950 dark:border-amber-500 dark:bg-amber-500/20 dark:text-amber-100'
      }`}
    >
      <p className="m-0 min-w-0 flex-none">
        {backendDown ? (
          <span className="font-semibold">Local backend unreachable</span>
        ) : (
          <span className="font-semibold">Lost SSH connection to {serverLabel}</span>
        )}
      </p>
      <button
        type="button"
        onClick={() => void handleRetry()}
        disabled={retrying}
        className="inline-flex h-6.5 flex-none cursor-pointer items-center gap-1 rounded-md border border-current px-2.5 text-xs font-semibold transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {retrying ? (
          <>
            <Loader2 className="h-3 w-3 animate-spin" /> Retrying...
          </>
        ) : (
          <>
            <RefreshCw className="h-3 w-3" /> Retry
          </>
        )}
      </button>
    </div>
  );
}

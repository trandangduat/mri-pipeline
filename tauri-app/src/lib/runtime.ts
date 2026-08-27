import type {
  EnvironmentResponse,
  GpuInfo,
  HardwareStatus,
  RemoteResultState,
  RemoteValidateResponse,
  RuntimeTarget,
} from '../types/backend';

export interface TargetHardware {
  label: RuntimeTarget;
  connected: boolean;
  logicalCores: number | null;
  totalRamBytes: number | null;
  gpus: GpuInfo[];
}

function normalizedGpus(gpus: GpuInfo[] | undefined): GpuInfo[] {
  return (gpus || []).map((gpu) => ({
    name: String(gpu.name || ''),
    total_memory_mib: Number(gpu.total_memory_mib ?? 0) || null,
    free_memory_mib: Number(gpu.free_memory_mib ?? 0) || null,
  }));
}

export function currentTargetHardware({
  runtimeTarget,
  environment,
  remoteResult,
}: {
  runtimeTarget: RuntimeTarget;
  environment?: EnvironmentResponse | null | undefined;
  remoteResult?: RemoteValidateResponse | Partial<RemoteResultState> | null | undefined;
}): TargetHardware {
  if (runtimeTarget === 'Server') {
    return {
      connected: remoteResult?.connected === true,
      logicalCores: Number(remoteResult?.hardware?.logical_cores || 0) || null,
      totalRamBytes: Number(remoteResult?.hardware?.total_ram_bytes || 0) || null,
      gpus: normalizedGpus(remoteResult?.hardware?.gpus),
      label: 'Server',
    };
  }
  const hardware: HardwareStatus = environment?.hardware || {
    hostname: '',
    logical_cores: null,
    physical_cores: null,
    total_ram_bytes: null,
  };
  return {
    connected: true,
    logicalCores: Number(hardware.logical_cores || 0) || null,
    totalRamBytes: Number(hardware.total_ram_bytes || 0) || null,
    gpus: normalizedGpus(hardware.gpus),
    label: 'Local',
  };
}

export const RAM_PERCENT_MIN = 1;
export const RAM_PERCENT_MAX = 100;
export const DEFAULT_RAM_PERCENT = 80;
export const DEFAULT_CPU_THREADS = 4;
/** Values that exceed a hard limit snap back to this share of the limit (90%). */
export const SAFE_LIMIT_SHARE = 0.9;

/** The "safe" milestone for a hard limit: 90% of it, at least 1. */
export function safeLimitMark(max: number | null): number | null {
  if (max == null) return null;
  return Math.max(RAM_PERCENT_MIN, Math.floor(max * SAFE_LIMIT_SHARE));
}

/** Core cap of a runtime target: server cores when connected, local cores otherwise. */
export function cpuThreadCapForTarget({
  runtimeTarget,
  environment,
  remoteResult,
}: {
  runtimeTarget: RuntimeTarget;
  environment?: EnvironmentResponse | null | undefined;
  remoteResult?: RemoteValidateResponse | Partial<RemoteResultState> | null | undefined;
}): number | null {
  return currentTargetHardware({runtimeTarget, environment, remoteResult}).logicalCores;
}

/**
 * Re-validate stored form values after the runtime target changes so values
 * valid on the previous machine (e.g. 50 threads / 56-core server) are
 * resolved against the new machine (e.g. snapped to 7 on an 8-core local).
 */
export function reclampCpuThreadsForTarget({
  cpuThreads,
  threadCap,
}: {
  cpuThreads: number | string;
  threadCap: number | null;
}): number {
  return clampBoundedIntValue(cpuThreads, safeLimitMark(threadCap) ?? DEFAULT_CPU_THREADS, threadCap);
}

/**
 * Keep only digits while typing; '' is allowed mid-edit.
 * Values beyond max snap back to the safe 90% mark instead of the raw max.
 */
export function sanitizeBoundedIntText(raw: string, max: number | null): string {
  const digits = String(raw).replace(/[^0-9]/g, '').replace(/^0+(?=\d)/, '');
  if (!digits) return '';
  const parsed = parseInt(digits, 10);
  if (!Number.isFinite(parsed)) return '';
  if (max != null && parsed > max) return String(safeLimitMark(max));
  return digits;
}

/**
 * Coerce any stored value into a valid int within [1, max]; falls back when
 * empty/invalid. Values beyond max resolve to the safe 90% mark.
 */
export function clampBoundedIntValue(value: number | string | null | undefined, fallback: number, max: number | null): number {
  if (value === null || value === undefined || String(value).trim() === '') {
    return clampBoundedIntValue(fallback, fallback, max);
  }
  const parsed = Math.floor(Number(value));
  if (!Number.isFinite(parsed)) return clampBoundedIntValue(fallback, fallback, max);
  if (max != null && parsed > max) return Math.max(safeLimitMark(max) ?? RAM_PERCENT_MIN, RAM_PERCENT_MIN);
  return Math.max(parsed, RAM_PERCENT_MIN);
}

export interface RuntimeLimitInput {
  runtimeTarget: RuntimeTarget;
  hardware: TargetHardware;
  cpuThreads: number | string;
  ramPercent: number | string;
}

/** Hard validation: values outside these bounds must block starting a run. */
export function runtimeLimitErrors({hardware, cpuThreads, ramPercent}: RuntimeLimitInput): string[] {
  const errors: string[] = [];
  const requestedThreads = Math.floor(Number(cpuThreads || 0));
  const requestedRam = Number(ramPercent || 0);
  if (!Number.isFinite(requestedRam) || requestedRam < RAM_PERCENT_MIN || requestedRam > RAM_PERCENT_MAX) {
    errors.push(`RAM allocation must be between ${RAM_PERCENT_MIN} and ${RAM_PERCENT_MAX}%.`);
  }
  if (!Number.isFinite(requestedThreads) || requestedThreads < 1) {
    errors.push('CPU threads must be a whole number of at least 1.');
  } else if (hardware.logicalCores && requestedThreads > hardware.logicalCores) {
    errors.push(
      `CPU threads (${requestedThreads}) cannot exceed the machine's ${hardware.logicalCores} logical cores.`,
    );
  }
  return errors;
}

export function runtimeWarnings({
  runtimeTarget,
  hardware,
  cpuThreads,
  ramPercent,
}: {
  runtimeTarget: RuntimeTarget;
  hardware: TargetHardware;
  cpuThreads: number | string;
  ramPercent: number | string;
}): string[] {
  const warnings: string[] = [];
  const requestedThreads = Number(cpuThreads || 0);
  const requestedRam = Number(ramPercent || 0);
  if (hardware.logicalCores && requestedThreads > hardware.logicalCores * 0.9) {
    warnings.push("CPU threads is above 90% of machine's max CPU threads.");
  }
  if (requestedRam > 90) {
    warnings.push("RAM allocation is above 90% of machine's RAM.");
  }
  if (runtimeTarget === 'Server' && !hardware.connected) {
    warnings.push('Server runtime selected, but SSH is not connected yet.');
  }
  return warnings;
}

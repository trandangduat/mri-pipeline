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

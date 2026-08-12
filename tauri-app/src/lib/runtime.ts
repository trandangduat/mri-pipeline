import type {
  EnvironmentResponse,
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
    warnings.push(`CPU threads ${requestedThreads} is above 90% of target max (${hardware.logicalCores}).`);
  }
  if (requestedRam > 90) {
    warnings.push(`RAM ${requestedRam}% is above 90% of target memory.`);
  }
  if (runtimeTarget === 'Server' && !hardware.connected) {
    warnings.push('Server runtime selected, but SSH is not connected yet.');
  }
  return warnings;
}

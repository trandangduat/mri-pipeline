export function currentTargetHardware({runtimeTarget, environment, remoteResult}) {
  if (runtimeTarget === 'Server') {
    return {
      connected: remoteResult?.connected === true,
      logicalCores: Number(remoteResult?.logicalCores || 0) || null,
      totalRamBytes: Number(remoteResult?.totalRamBytes || 0) || null,
      label: 'Server',
    };
  }
  const hardware = environment?.hardware || {};
  return {
    connected: true,
    logicalCores: Number(hardware.logical_cores || 0) || null,
    totalRamBytes: Number(hardware.total_ram_bytes || 0) || null,
    label: 'Local',
  };
}

export function runtimeWarnings({runtimeTarget, hardware, cpuThreads, ramPercent}) {
  const warnings = [];
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

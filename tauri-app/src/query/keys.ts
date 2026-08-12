export const queryKeys = {
  health: () => ['health'] as const,
  environment: {
    local: () => ['environment', 'local'] as const,
  },
  metadata: () => ['metadata'] as const,
  jobs: {
    local: () => ['jobs', 'local'] as const,
    remote: (fingerprint: string) => ['jobs', 'remote', fingerprint] as const,
    events: (jobId: string) => ['jobs', 'events', jobId] as const,
    log: (jobId: string, offset: number, maxBytes: number) => ['jobs', 'log', jobId, offset, maxBytes] as const,
  },
  tools: {
    images: (target: string, selectedToolsHash: string) => ['tools', 'images', target, selectedToolsHash] as const,
  },
  remote: {
    validate: () => ['remote', 'validate'] as const,
  },
} as const;

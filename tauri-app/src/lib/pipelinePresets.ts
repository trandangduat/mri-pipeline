import type {AppMetadata} from '../types/backend';

export function presetDefaultAtlases(
  metadata: AppMetadata | null | undefined,
  pipelineMode: string,
): Record<string, string[]> {
  const next: Record<string, string[]> = {};

  for (const statKey of Object.keys(metadata?.stats_vectors || {})) {
    next[statKey] = [];
  }

  const defaults = metadata?.presets?.[pipelineMode]?.default_atlases || {};
  for (const [statKey, atlases] of Object.entries(defaults)) {
    next[statKey] = Array.isArray(atlases) ? [...atlases] : [];
  }

  return next;
}

export function isPresetMode(metadata: AppMetadata | null | undefined, pipelineMode: string): boolean {
  return pipelineMode !== 'Custom' && Boolean(metadata?.presets?.[pipelineMode]);
}

export function presetHandlesStat(
  metadata: AppMetadata | null | undefined,
  pipelineMode: string,
  statKey: string,
): boolean {
  return Boolean(metadata?.presets?.[pipelineMode]?.stats?.includes(statKey));
}

export function isPresetDefaultAtlas(
  metadata: AppMetadata | null | undefined,
  pipelineMode: string,
  statKey: string,
  atlasKey: string,
): boolean {
  return Boolean(metadata?.presets?.[pipelineMode]?.default_atlases?.[statKey]?.includes(atlasKey));
}

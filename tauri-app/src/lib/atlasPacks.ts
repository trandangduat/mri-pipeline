/** Map a pipeline surface-atlas key to a downloadable atlas pack id. */
export function resolveSurfaceAtlasPackId(atlasKey: string): string | null {
  const norm = atlasKey.trim().toLowerCase();
  if (!norm.includes('schaefer') || norm.includes('cat12')) {
    return null;
  }
  if (norm === 'schaefer2018') {
    return 'schaefer2018';
  }
  if (/^schaefer2018_\d+parcels_\d+networks$/.test(norm)) {
    return norm;
  }
  return 'schaefer2018_400parcels_17networks';
}

/** Map a pipeline volume-atlas key to a downloadable atlas pack id. */
export function resolveVolumeAtlasPackId(atlasKey: string): string | null {
  const norm = atlasKey.trim().toLowerCase();
  const mniKeys = [
    'harvard_oxford',
    'brainnetome',
    'pauli',
    'juelich',
    'aal',
    'schaefer2018_100_7',
  ];
  if (mniKeys.some((k) => norm.includes(k))) {
    return 'mni_volume_pack';
  }
  return null;
}

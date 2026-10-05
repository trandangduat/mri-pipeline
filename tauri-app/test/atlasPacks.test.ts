import {describe, expect, it} from 'vitest';
import {resolveSurfaceAtlasPackId} from '../src/lib/atlasPacks';

describe('resolveSurfaceAtlasPackId', () => {
  it('maps Schaefer atlas keys to matching pack ids', () => {
    expect(resolveSurfaceAtlasPackId('schaefer2018_400parcels_17networks')).toBe(
      'schaefer2018_400parcels_17networks',
    );
    expect(resolveSurfaceAtlasPackId('schaefer2018_600parcels_17networks')).toBe(
      'schaefer2018_600parcels_17networks',
    );
    expect(resolveSurfaceAtlasPackId('schaefer2018')).toBe('schaefer2018');
  });

  it('ignores CAT12 volume Schaefer atlases', () => {
    expect(resolveSurfaceAtlasPackId('cat12_schaefer2018_200parcels_17networks')).toBeNull();
  });

  it('falls back to the default FreeSurfer Schaefer pack for unknown Schaefer keys', () => {
    expect(resolveSurfaceAtlasPackId('schaefer2018_legacy_alias')).toBe('schaefer2018_400parcels_17networks');
  });
});

import {describe, expect, it} from 'vitest';
import {
  contentPackMutationResponseSchema,
  contentPacksListResponseSchema,
} from '../src/api/schemas';

describe('content pack schemas', () => {
  it('accepts a list payload', () => {
    const parsed = contentPacksListResponseSchema.parse({
      ok: true,
      packs: [
        {
          pack_id: 'surface-atlases',
          known: true,
          installed: false,
          version: null,
          redistribution_note: 'rights required',
        },
      ],
    });
    expect(parsed.packs?.[0]?.pack_id).toBe('surface-atlases');
  });

  it('accepts install/remove responses', () => {
    expect(contentPackMutationResponseSchema.parse({ok: true, pack_id: 'surface-atlases', version: '1.0.0'}).ok).toBe(
      true,
    );
    expect(contentPackMutationResponseSchema.parse({ok: false, error: 'boom'}).error).toBe('boom');
  });
});

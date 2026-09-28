import React, {useCallback, useEffect, useState} from 'react';
import {Package, Loader2, FolderOpen, Trash2} from 'lucide-react';
import {Button} from './ui';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api';
import type {ContentPackStatus} from '../types/backend';

const client = new BackendClient(DEFAULT_BACKEND_URL);

/**
 * Minimal explicit-action hook for signed content packs.
 * Install is local-file only in the UI for now (offline import); HTTPS installs
 * remain available via the backend API for automation.
 */
export function ContentPacksPanel() {
  const [packs, setPacks] = useState<ContentPackStatus[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const refresh = useCallback(async () => {
    setError('');
    try {
      const result = await client.listContentPacks();
      if (!result.ok) {
        setError(result.error || 'Failed to list content packs');
        return;
      }
      setPacks(result.packs || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onImport = async (packId: string, fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) {
      return;
    }
    // Expect the user to pick the .zip archive; sibling index/sig must be provided
    // via path-based install in packaged builds. For the minimal hook we support
    // inline install when the caller posts archive+index+sig through a folder
    // selection is not available in the browser — use three-file picker pattern:
    // user selects the archive; we look for identically named index.json and .sig
    // is not possible from a single file input. Instead require a JSON manifest
    // bundle is out of scope — offer archive_base64 only when all three File
    // objects are selected via webkitdirectory is complex.
    //
    // Practical minimal hook: accept one .zip and require the operator to also
    // paste isn't great. Use backend local_archive paths via a text prompt for
    // internal-test builds.
    const archivePath = window.prompt(
      `Internal-test install for ${packId}.\nEnter the full path to archive.zip `
      + `(index.json and index.json.sig must sit beside it):`,
    );
    if (!archivePath) {
      return;
    }
    const base = archivePath.replace(/[\\/][^\\/]+$/, '');
    const sep = archivePath.includes('\\') ? '\\' : '/';
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const result = await client.installContentPack({
        pack_id: packId,
        local_archive: archivePath,
        local_index: `${base}${sep}index.json`,
        local_signature: `${base}${sep}index.json.sig`,
      });
      if (!result.ok) {
        setError(result.error || 'Install failed');
      } else {
        setMessage(`Installed ${packId} ${result.version || ''}`.trim());
        await refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onRemove = async (packId: string) => {
    if (!window.confirm(`Remove content pack ${packId}? User outputs and secrets are not touched.`)) {
      return;
    }
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const result = await client.removeContentPack(packId);
      if (!result.ok) {
        setError(result.error || 'Remove failed');
      } else {
        setMessage(`Removed ${packId}`);
        await refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <div className="mb-2.5 flex items-center justify-between">
        <h2 className="flex items-center gap-1.5 text-base font-semibold text-cursor-ink">
          <Package className="h-4 w-4 text-cursor-primary" />
          Content Packs
        </h2>
        <Button variant="ghost" onClick={() => void refresh()} disabled={busy}>
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Refresh'}
        </Button>
      </div>
      <div className="rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 space-y-3">
        <p className="text-xs text-cursor-muted">
          Optional signed packs (for example surface-atlases) install only after an explicit action.
          Redistribution rights are still required before shipping real proprietary atlas binaries.
        </p>
        {error ? <div className="text-xs text-cursor-semantic-error">{error}</div> : null}
        {message ? <div className="text-xs text-cursor-semantic-success">{message}</div> : null}
        {packs.map((pack) => (
          <div key={pack.pack_id} className="flex flex-wrap items-center justify-between gap-2 border-t border-cursor-hairline-soft pt-3">
            <div className="min-w-0">
              <div className="text-sm font-medium text-cursor-ink">{pack.pack_id}</div>
              <div className="text-xs text-cursor-muted">
                {pack.installed
                  ? `Installed version ${pack.version || 'unknown'}`
                  : 'Not installed'}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                icon={<FolderOpen className="h-3.5 w-3.5" />}
                disabled={busy}
                onClick={() => void onImport(pack.pack_id, null)}
              >
                Import local pack
              </Button>
              <Button
                variant="ghost"
                icon={<Trash2 className="h-3.5 w-3.5" />}
                disabled={busy || !pack.installed}
                onClick={() => void onRemove(pack.pack_id)}
              >
                Remove
              </Button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

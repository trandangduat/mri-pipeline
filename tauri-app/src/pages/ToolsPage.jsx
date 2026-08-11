import React from 'react';
import {Container, Download, RefreshCw, Search, Terminal, Trash2} from 'lucide-react';
import {Panel, Button, inputCls, StatusPill} from '../components/ui.jsx';
import {useApp} from '../AppContext.jsx';
import {filterImages, imageRowKey, selectAllVisible, unselectVisible, selectMissing, toggleImageKey} from '../lib/tools.js';

export function ToolsPage() {
  const {environment, selectedRuntimeTarget, latestImages, imageSearch, setImageSearch, imageSelection, setImageSelection, toolMessage, imageLogText, appendImageLog, refreshTools, refreshEnvironment, busy} = useApp();

  const python = environment?.python || {ok: false, path: '', version: ''};
  const images = filterImages(latestImages, imageSearch);
  const selectedCount = imageSelection.size;
  const allVisibleSelected = images.length > 0 && images.every((image) => imageSelection.has(imageRowKey(image, 0)));

  return (
    <div className="grid gap-6">
      <Panel
        icon={<span className="inline-grid h-8 w-8 place-items-center rounded-md bg-cursor-timeline-read text-xs font-semibold text-cursor-ink">Py</span>}
        title="Python Environment"
        titleRight={
          <Button variant="primary" icon={<RefreshCw className="h-4 w-4" />} onClick={refreshEnvironment} disabled={busy.checkEnv}>
            Check Environment
          </Button>
        }
      >
        <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(14rem,1fr))]">
          <div className="flex flex-col gap-2 rounded-xl border border-cursor-hairline bg-white p-4">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Runtime Target</span>
            <div className="flex min-w-0 items-center">
              <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-hairline-soft px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-ink">
                {selectedRuntimeTarget()}
              </span>
            </div>
          </div>
          <div className="flex flex-col gap-2 rounded-xl border border-cursor-hairline bg-white p-4">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Python Status</span>
            <div className="flex min-w-0 items-center">
              <StatusPill state={python.ok ? 'installed' : 'missing'}>{python.ok ? `Ready (${python.version || 'unknown'})` : 'Missing'}</StatusPill>
            </div>
          </div>
          <div className="flex flex-col gap-2 rounded-xl border border-cursor-hairline bg-white p-4">
            <span className="text-xs font-medium uppercase tracking-wider text-cursor-muted">Executable Path</span>
            <div className="flex min-w-0 items-center">
              <code className="w-full truncate rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft px-2.5 py-1 font-mono text-xs text-cursor-ink">
                {python.path || 'Unknown'}
              </code>
            </div>
          </div>
        </div>
      </Panel>

      <Panel
        icon={<Container className="h-5 w-5 text-cursor-primary" />}
        title="Docker Images"
        titleRight={
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center rounded-full border border-cursor-primary/20 bg-cursor-primary/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-primary">
              {selectedRuntimeTarget()}
            </span>
            <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-hairline px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-body">
              {images.length} image{images.length === 1 ? '' : 's'}
            </span>
            <Button id="refreshToolsButton" variant="primary" icon={<RefreshCw className="h-4 w-4" />} onClick={refreshTools} disabled={busy.refreshTools}>
              Refresh Images
            </Button>
          </div>
        }
      >
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <label className="relative m-0 block w-full max-w-[22rem]">
            <input
              id="imageSearch"
              type="search"
              placeholder="Search Docker images or tools..."
              value={imageSearch}
              onChange={(e) => setImageSearch(e.target.value)}
              className={`${inputCls} pr-9`}
            />
            <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cursor-muted" />
          </label>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              onClick={() => selectAllVisible({images, keys: imageSelection, setKeys: setImageSelection})}
            >
              Select All
            </Button>
            <Button variant="ghost" onClick={() => unselectVisible({images, keys: imageSelection, setKeys: setImageSelection})}>
              Unselect All
            </Button>
            <Button variant="ghost" onClick={() => selectMissing(images, imageSelection, setImageSelection)}>
              Select Missing
            </Button>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="ink" icon={<Download className="h-4 w-4" />} onClick={() => appendImageLog('Download action is not enabled in this safety slice.')}>
              Download
            </Button>
            <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} onClick={() => appendImageLog('Delete action is not enabled in this safety slice.')}>
              Delete
            </Button>
          </div>
        </div>

        <div className="overflow-auto rounded-lg border border-cursor-hairline">
          <table className="w-full border-collapse bg-white">
            <thead>
              <tr>
                <th className="w-10 border-b border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-cursor-muted whitespace-nowrap">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={(e) => {
                      if (e.target.checked) {
                        selectAllVisible({images, keys: imageSelection, setKeys: setImageSelection});
                      } else {
                        unselectVisible({images, keys: imageSelection, setKeys: setImageSelection});
                      }
                    }}
                    className="h-auto w-auto"
                  />
                </th>
                <th className="border-b border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-cursor-muted whitespace-nowrap">Tool Name</th>
                <th className="border-b border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-cursor-muted whitespace-nowrap">Docker Repository / Tag</th>
                <th className="border-b border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-cursor-muted whitespace-nowrap">Image ID</th>
                <th className="border-b border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-cursor-muted whitespace-nowrap">Size</th>
                <th className="border-b border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-cursor-muted whitespace-nowrap">Installed</th>
                <th className="border-b border-cursor-hairline-soft bg-cursor-canvas-soft px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-cursor-muted whitespace-nowrap">Status</th>
              </tr>
            </thead>
            <tbody id="toolTableBody">
              {!latestImages.length ? (
                <tr>
                  <td colSpan="7" className="border-b border-cursor-hairline-soft px-4 py-3 text-sm text-cursor-ink">
                    {toolMessage}
                  </td>
                </tr>
              ) : images.length ? (
                images.map((image, index) => {
                  const key = imageRowKey(image, index);
                  const installed = image.status === 'Installed';
                  return (
                    <tr key={key}>
                      <td className="border-b border-cursor-hairline-soft px-4 py-3 text-center align-middle">
                        <input
                          type="checkbox"
                          checked={imageSelection.has(key)}
                          onChange={() => setImageSelection(toggleImageKey(imageSelection, key))}
                          className="h-auto w-auto"
                        />
                      </td>
                      <td className="border-b border-cursor-hairline-soft px-4 py-3 align-middle text-sm font-medium text-cursor-ink">
                        {(image.tools || []).join(', ') || 'Tool'}
                      </td>
                      <td className="border-b border-cursor-hairline-soft px-4 py-3 align-middle font-mono text-xs text-cursor-body">
                        {image.image}
                      </td>
                      <td className="border-b border-cursor-hairline-soft px-4 py-3 align-middle text-sm text-cursor-muted">Unknown</td>
                      <td className="border-b border-cursor-hairline-soft px-4 py-3 align-middle text-sm text-cursor-muted">Unknown</td>
                      <td className="border-b border-cursor-hairline-soft px-4 py-3 align-middle">
                        <StatusPill state={installed ? 'installed' : 'missing'}>{installed ? 'Yes' : 'No'}</StatusPill>
                      </td>
                      <td className="border-b border-cursor-hairline-soft px-4 py-3 align-middle">
                        <StatusPill state={image.status || 'unknown'}>{image.status || 'Unknown'}</StatusPill>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan="7" className="border-b border-cursor-hairline-soft px-4 py-3 text-sm text-cursor-ink">
                    No Docker images match your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <label className="mt-6 grid gap-3 rounded-xl border border-cursor-hairline bg-white p-5 text-cursor-ink">
          <span className="flex items-center gap-2 text-[18px] font-semibold text-cursor-ink">
            <Terminal className="h-5 w-5 text-cursor-primary" />
            Image Activity Logs
          </span>
          <textarea
            id="imageLog"
            className="mt-2 min-h-32 h-auto w-full resize-y rounded-xl border-0 bg-white p-0 font-mono text-[13px] leading-[1.5] text-cursor-ink"
            readOnly
            value={imageLogText}
          />
        </label>
      </Panel>
    </div>
  );
}

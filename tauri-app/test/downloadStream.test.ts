import {expect, test} from 'vitest';
import {BackendClient} from '../src/api/client';

test('startRemoteDownloadStream sends POST to download endpoint', async () => {
  const calls: Array<{url: string; options: RequestInit}> = [];
  const client = new BackendClient('http://backend', async (url: RequestInfo | URL, options?: RequestInit) => {
    calls.push({url: String(url), options: options || {}});
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: complete\ndata: {"ok": true}\n\n'));
        controller.close();
      },
    });
    return {ok: true, body: stream} as unknown as Response;
  });

  const events: Array<{event: string; data: Record<string, unknown>}> = [];
  await client.startRemoteDownloadStream(
    {
      host: 'server',
      port: 22,
      username: 'tester',
      remote_job_dir: '/workspace/job_1',
      local_target_dir: '/tmp/outputs',
    },
    (event, data) => events.push({event, data}),
    () => {},
  );

  expect(calls[0]?.url).toBe('http://backend/remote/jobs/download/stream');
  expect(calls[0]?.options.method).toBe('POST');
  expect(events).toEqual([{event: 'complete', data: {ok: true}}]);
});

test('startRemoteDownloadStream reports errors', async () => {
  const client = new BackendClient('http://backend', async () => {
    return {ok: false, status: 500} as unknown as Response;
  });

  const errors: string[] = [];
  await client.startRemoteDownloadStream({}, () => {}, (err) => errors.push(err));

  expect(errors).toEqual(['HTTP 500']);
});

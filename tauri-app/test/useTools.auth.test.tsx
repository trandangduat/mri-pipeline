import React from 'react';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {act, renderHook} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {resetBackendTokenForTests} from '../src/api/backendToken';
import {usePullImageStream} from '../src/query/useTools';

function wrapper({children}: {children: React.ReactNode}) {
  const queryClient = new QueryClient({defaultOptions: {queries: {retry: false}, mutations: {retry: false}}});
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function streamResponse(payload: Record<string, unknown>): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(`event: complete\ndata: ${JSON.stringify(payload)}\n\n`));
      controller.close();
    },
  });
  return {ok: true, body} as unknown as Response;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  resetBackendTokenForTests();
});

test('Tools pull stream sends the sidecar token', async () => {
  vi.stubEnv('VITE_NEUROFLOW_API_TOKEN', 'tools-stream-token');
  const fetchMock = vi.fn(async () => streamResponse({ok: true}));
  vi.stubGlobal('fetch', fetchMock);
  const {result} = renderHook(() => usePullImageStream(), {wrapper});

  await act(async () => {
    await result.current.pull('example/image:1');
  });

  expect(fetchMock).toHaveBeenCalledOnce();
  const [url, options] = fetchMock.mock.calls[0] || [];
  expect(url).toBe('http://127.0.0.1:8765/tools/local/pull');
  expect(new Headers((options as RequestInit).headers).get('Authorization')).toBe('Bearer tools-stream-token');
});

test('Tools server pull poll sends the sidecar token', async () => {
  vi.useFakeTimers();
  vi.stubEnv('VITE_NEUROFLOW_API_TOKEN', 'tools-poll-token');
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(streamResponse({ok: true, status: 'pulling'}))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ok: true, exit_code: 0, next_offset: 0}),
    } as Response);
  vi.stubGlobal('fetch', fetchMock);
  const {result} = renderHook(() => usePullImageStream(), {wrapper});

  await act(async () => {
    await result.current.pull('example/image:1', {target: 'Server', remote: {host: 'server'}});
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3_000);
  });

  expect(fetchMock).toHaveBeenCalledTimes(2);
  const [url, options] = fetchMock.mock.calls[1] || [];
  expect(url).toBe('http://127.0.0.1:8765/tools/server/pull/status');
  expect(new Headers((options as RequestInit).headers).get('Authorization')).toBe('Bearer tools-poll-token');
});

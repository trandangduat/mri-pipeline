import {invoke} from '@tauri-apps/api/core';

let tokenPromise: Promise<string> | null = null;

/**
 * Obtain the short-lived sidecar token from the native shell.
 *
 * A development server receives the same token through Vite's process-only
 * environment. Production code never embeds it in the web bundle.
 */
export function getBackendToken(): Promise<string> {
  const devToken = import.meta.env.VITE_NEUROFLOW_API_TOKEN;
  if (devToken) return Promise.resolve(devToken);
  if (typeof window === 'undefined' || !('__TAURI_INTERNALS__' in window)) {
    // Unit tests use a mocked fetch implementation without a Tauri runtime.
    return Promise.resolve('');
  }
  if (!tokenPromise) {
    tokenPromise = invoke<string>('backend_token');
  }
  return tokenPromise;
}

/**
 * Add the per-launch sidecar credential to a browser request.
 *
 * Keep this beside token retrieval so every exceptional raw-fetch path uses
 * exactly the same authentication contract as BackendClient.  In unit tests
 * and non-Tauri server rendering there is intentionally no token to attach.
 */
export async function authenticatedBackendHeaders(headers?: HeadersInit): Promise<Headers> {
  const result = new Headers(headers);
  const token = await getBackendToken();
  if (token) result.set('Authorization', `Bearer ${token}`);
  return result;
}

export function resetBackendTokenForTests(): void {
  tokenPromise = null;
}

export async function waitForBackendReadiness({
  fetchImpl = globalThis.fetch,
  attempts = 20,
  delayMs = 250,
  sleep = (delay) => new Promise((resolve) => setTimeout(resolve, delay)),
} = {}) {
  let lastError = 'The application backend did not become ready.';
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const healthResponse = await fetchImpl('http://127.0.0.1:8765/health');
      const health = await healthResponse.json();
      if (!healthResponse.ok || health.ok !== true) throw new Error('The backend health check did not succeed.');

      const capabilitiesResponse = await fetchImpl('http://127.0.0.1:8765/capabilities/runtime');
      const capabilities = await capabilitiesResponse.json();
      if (!capabilitiesResponse.ok) throw new Error('The backend capability check did not succeed.');
      if (capabilities.ok === true) return {ok: true, missing: []};

      const missing = Array.isArray(capabilities.components)
        ? capabilities.components.filter((component) => component?.ok !== true).map((component) => component?.label || component?.id).filter(Boolean)
        : [];
      if (missing.length > 0) return {ok: false, missing, error: 'Required application backend components are unavailable.'};
      throw new Error('The backend capability check did not succeed.');
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      if (attempt + 1 < attempts) await sleep(delayMs);
    }
  }
  return {ok: false, missing: [], error: lastError};
}

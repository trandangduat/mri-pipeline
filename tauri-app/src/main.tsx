import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';
import '@fontsource/jetbrains-mono/latin-400.css';
import '@fontsource/jetbrains-mono/latin-500.css';
import {App} from './App';
import {usePipelineFormStore} from './stores/pipelineFormStore';
import {useRemoteStore} from './stores/remoteStore';
import {useToolsStore} from './stores/toolsStore';
import {queryClient} from './query/queryClient';

if (typeof window !== 'undefined' && import.meta.env.DEV) {
  Object.assign(window, {
    __stores: {usePipelineFormStore, useRemoteStore, useToolsStore},
    __queryClient: queryClient,
  });
}

const container = document.getElementById('root');
if (!container) {
  throw new Error('Missing #root mount point.');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

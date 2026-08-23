import React from 'react';
import {AppProviders} from './providers/AppProviders';
import {AppRouter} from './router/AppRouter';
import {useCloseGuard} from './hooks/useCloseGuard';

export function App() {
  useCloseGuard(true);
  return (
    <AppProviders>
      <AppRouter />
    </AppProviders>
  );
}

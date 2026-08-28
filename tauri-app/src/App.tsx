import React from 'react';
import {AppProviders} from './providers/AppProviders';
import {AppRouter} from './router/AppRouter';

export function App() {
  return (
    <AppProviders>
      <AppRouter />
    </AppProviders>
  );
}


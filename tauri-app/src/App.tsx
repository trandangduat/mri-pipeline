import React from 'react';
import {AppProviders} from './providers/AppProviders';
import {AppRouter} from './router/AppRouter';
import {Toaster} from './components/Toaster';

export function App() {
  return (
    <AppProviders>
      <AppRouter />
      <Toaster />
    </AppProviders>
  );
}


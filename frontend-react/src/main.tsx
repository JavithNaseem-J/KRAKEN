import React from 'react';
import ReactDOM from 'react-dom/client';

import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { PersonaProvider } from './context/PersonaContext';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <PersonaProvider>
        <App />
      </PersonaProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);

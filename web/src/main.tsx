import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { Preview } from './Preview';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {import.meta.env.MODE === 'preview' ? <Preview /> : <App />}
  </StrictMode>,
);

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { Ambient } from './components/Ambient'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Ambient />
    <App />
  </StrictMode>,
)

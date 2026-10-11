import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RoadmapHarness } from './RoadmapHarness'

createRoot(document.getElementById('root')!).render(<StrictMode><RoadmapHarness /></StrictMode>)

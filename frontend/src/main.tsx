import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Bricolage Grotesque: a letra de todo o texto (eixo opsz: mais calma no corpo, mais personalidade nos títulos).
// Bodoni Moda: só o nome Atena. IBM Plex Mono: só dados de máquina (IDs, desenho ASCII).
import '@fontsource-variable/bricolage-grotesque/standard.css'
import '@fontsource-variable/bodoni-moda/opsz.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

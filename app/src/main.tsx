import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { registerSW } from 'virtual:pwa-register'
import App from './App'
import './index.css'

// Auto-update service worker: checks every 15 min, reloads on new version
registerSW({
  onRegisteredSW(_url, registration) {
    if (registration) {
      setInterval(() => registration.update(), 15 * 60 * 1000)
    }
  },
  onNeedRefresh() {
    // New version available — reload immediately
    window.location.reload()
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)

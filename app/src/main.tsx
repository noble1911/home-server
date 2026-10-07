import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { registerSW } from 'virtual:pwa-register'
import App from './App'
import { isNativeApp, openExternal } from './native/butlerNative'
import './index.css'

if (isNativeApp) {
  // In the Android app, links that would open a new tab go to the system browser.
  window.open = (url?: string | URL) => {
    if (url) openExternal(String(url))
    return null
  }
} else {
  registerSW({ immediate: true })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)

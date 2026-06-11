import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

// 在 React 掛載前先套用主題，避免深色使用者看到淺色閃爍
document.documentElement.dataset.theme = localStorage.getItem('craftflow_theme') ?? 'light'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

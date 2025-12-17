import { useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Repositories from './pages/Repositories'
import Vulnerabilities from './pages/Vulnerabilities'
import ScanQueue from './pages/ScanQueue'
import TriggerScan from './pages/TriggerScan'

function Navigation() {
  const location = useLocation()
  
  return (
    <nav className="nav">
      <Link to="/">
        <button className={location.pathname === '/' ? 'active' : ''}>
          Dashboard
        </button>
      </Link>
      <Link to="/repositories">
        <button className={location.pathname === '/repositories' ? 'active' : ''}>
          Repositories
        </button>
      </Link>
      <Link to="/vulnerabilities">
        <button className={location.pathname === '/vulnerabilities' ? 'active' : ''}>
          Vulnerabilities
        </button>
      </Link>
      <Link to="/queue">
        <button className={location.pathname === '/queue' ? 'active' : ''}>
          Scan Queue
        </button>
      </Link>
      <Link to="/scan">
        <button className={location.pathname === '/scan' ? 'active' : ''}>
          Trigger Scan
        </button>
      </Link>
    </nav>
  )
}

function App() {
  return (
    <Router>
      <div>
        <header className="header">
          <div className="container">
            <h1>🔒 GitHub Security Scanner</h1>
            <p>Monitor and analyze GitHub repositories for security vulnerabilities</p>
            <Navigation />
          </div>
        </header>
        
        <div className="container">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/repositories" element={<Repositories />} />
            <Route path="/vulnerabilities" element={<Vulnerabilities />} />
            <Route path="/queue" element={<ScanQueue />} />
            <Route path="/scan" element={<TriggerScan />} />
          </Routes>
        </div>
      </div>
    </Router>
  )
}

export default App

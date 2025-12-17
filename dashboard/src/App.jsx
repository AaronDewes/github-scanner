import { useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Repositories from './pages/Repositories'
import Vulnerabilities from './pages/Vulnerabilities'
import ScanQueue from './pages/ScanQueue'
import TriggerScan from './pages/TriggerScan'

function Navigation() {
  const location = useLocation()
  
  const navItems = [
    { path: '/', label: 'Dashboard', icon: '📊' },
    { path: '/repositories', label: 'Repositories', icon: '📁' },
    { path: '/vulnerabilities', label: 'Vulnerabilities', icon: '🛡️' },
    { path: '/queue', label: 'Scan Queue', icon: '📋' },
    { path: '/scan', label: 'Trigger Scan', icon: '🔍' },
  ]
  
  return (
    <nav className="nav">
      {navItems.map(item => (
        <Link key={item.path} to={item.path}>
          <button className={location.pathname === item.path ? 'active' : ''}>
            <span>{item.icon}</span>
            {item.label}
          </button>
        </Link>
      ))}
    </nav>
  )
}

function App() {
  return (
    <Router>
      <div>
        <header className="header">
          <div className="container">
            <h1>
              <span>🔒</span>
              GitHub Security Scanner
            </h1>
            <p>Monitor and analyze GitHub repositories for security vulnerabilities in Actions workflows</p>
            <Navigation />
          </div>
        </header>
        
        <main className="container">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/repositories" element={<Repositories />} />
            <Route path="/vulnerabilities" element={<Vulnerabilities />} />
            <Route path="/queue" element={<ScanQueue />} />
            <Route path="/scan" element={<TriggerScan />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App

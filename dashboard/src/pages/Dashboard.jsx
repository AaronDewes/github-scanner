import { useState, useEffect } from 'react'
import { getStats } from '../api'

export default function Dashboard() {
  const [stats, setStats] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    try {
      setLoading(true)
      const response = await getStats()
      setStats(response.data.slice(0, 10)) // Top 10
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="loading">Loading statistics...</div>
  if (error) return <div className="error">Error: {error}</div>

  const totalVulns = stats.reduce((sum, s) => sum + s.total_vulnerabilities, 0)
  const totalCritical = stats.reduce((sum, s) => sum + s.critical_count, 0)
  const totalHigh = stats.reduce((sum, s) => sum + s.high_count, 0)
  const totalOpen = stats.reduce((sum, s) => sum + s.open_count, 0)

  return (
    <div>
      <h2>📊 Dashboard Overview</h2>
      
      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total Vulnerabilities</h3>
          <div className="value">{totalVulns.toLocaleString()}</div>
        </div>
        <div className="stat-card" style={{ '--accent': '#ef4444' }}>
          <h3>🔴 Critical</h3>
          <div className="value" style={{ color: 'var(--danger)' }}>{totalCritical.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <h3>🟠 High Severity</h3>
          <div className="value" style={{ color: '#f97316' }}>{totalHigh.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <h3>⚠️ Open Issues</h3>
          <div className="value" style={{ color: 'var(--warning)' }}>{totalOpen.toLocaleString()}</div>
        </div>
      </div>

      <div className="card">
        <h3>🏆 Top 10 Repositories by Vulnerabilities</h3>
        {stats.length === 0 ? (
          <div className="empty-state">No vulnerability data yet. Start scanning repositories!</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Repository</th>
                <th style={{ textAlign: 'center' }}>Total</th>
                <th style={{ textAlign: 'center' }}>Critical</th>
                <th style={{ textAlign: 'center' }}>High</th>
                <th style={{ textAlign: 'center' }}>Medium</th>
                <th style={{ textAlign: 'center' }}>Low</th>
                <th style={{ textAlign: 'center' }}>Open</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((stat, index) => (
                <tr key={stat.repository_id}>
                  <td>
                    <strong style={{ color: 'var(--gray-900)' }}>{stat.owner}</strong>
                    <span style={{ color: 'var(--gray-400)' }}>/</span>
                    <span style={{ color: 'var(--primary)' }}>{stat.name}</span>
                  </td>
                  <td style={{ textAlign: 'center', fontWeight: 600 }}>{stat.total_vulnerabilities}</td>
                  <td style={{ textAlign: 'center' }}>
                    {stat.critical_count > 0 ? (
                      <span className="badge critical">{stat.critical_count}</span>
                    ) : (
                      <span style={{ color: 'var(--gray-400)' }}>—</span>
                    )}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    {stat.high_count > 0 ? (
                      <span className="badge high">{stat.high_count}</span>
                    ) : (
                      <span style={{ color: 'var(--gray-400)' }}>—</span>
                    )}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    {stat.medium_count > 0 ? (
                      <span className="badge medium">{stat.medium_count}</span>
                    ) : (
                      <span style={{ color: 'var(--gray-400)' }}>—</span>
                    )}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    {stat.low_count > 0 ? (
                      <span className="badge low">{stat.low_count}</span>
                    ) : (
                      <span style={{ color: 'var(--gray-400)' }}>—</span>
                    )}
                  </td>
                  <td style={{ textAlign: 'center', fontWeight: 500, color: stat.open_count > 0 ? 'var(--danger)' : 'var(--gray-400)' }}>
                    {stat.open_count || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

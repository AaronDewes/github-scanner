import { useState, useEffect } from 'react'
import { getStats, getStatsSummary } from '../api'

export default function Dashboard() {
  const [stats, setStats] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    try {
      setLoading(true)
      const [statsResponse, summaryResponse] = await Promise.all([
        getStats(),
        getStatsSummary()
      ])
      setStats(statsResponse.data.slice(0, 10)) // Top 10
      setSummary(summaryResponse.data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="loading">Loading statistics...</div>
  if (error) return <div className="error">Error: {error}</div>

  // Use deduplicated summary stats for the overview cards
  const totalVulns = summary?.total_vulnerabilities || 0
  const totalCritical = summary?.critical_count || 0
  const totalHigh = summary?.high_count || 0
  const totalOpen = summary?.open_count || 0

  return (
    <div>
      <h2>📊 Dashboard Overview</h2>
      
      <div className="stats-grid">
        <div className="stat-card">
          <h3>Unique Vulnerabilities</h3>
          <div className="value">{totalVulns.toLocaleString()}</div>
          <small style={{ color: 'var(--gray-500)', fontSize: '0.75rem' }}>Deduplicated across repos/branches</small>
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

      {summary && (
        <div style={{ marginBottom: '24px', display: 'flex', gap: '16px', fontSize: '0.9rem', color: 'var(--gray-600)' }}>
          <span>📦 <strong>{summary.scanned_repositories}</strong> repositories scanned</span>
          <span>📁 <strong>{summary.total_repositories}</strong> total repositories</span>
        </div>
      )}

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

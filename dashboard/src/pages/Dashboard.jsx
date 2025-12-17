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
      <h2>Dashboard</h2>
      
      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total Vulnerabilities</h3>
          <div className="value">{totalVulns}</div>
        </div>
        <div className="stat-card">
          <h3>Critical</h3>
          <div className="value" style={{ color: '#d73a49' }}>{totalCritical}</div>
        </div>
        <div className="stat-card">
          <h3>High</h3>
          <div className="value" style={{ color: '#f66a0a' }}>{totalHigh}</div>
        </div>
        <div className="stat-card">
          <h3>Open Issues</h3>
          <div className="value" style={{ color: '#cf222e' }}>{totalOpen}</div>
        </div>
      </div>

      <div className="card">
        <h3>Top 10 Repositories by Vulnerabilities</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Repository</th>
              <th>Total</th>
              <th>Critical</th>
              <th>High</th>
              <th>Medium</th>
              <th>Low</th>
              <th>Open</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((stat) => (
              <tr key={stat.repository_id}>
                <td>{stat.owner}/{stat.name}</td>
                <td>{stat.total_vulnerabilities}</td>
                <td>
                  <span className="badge critical">{stat.critical_count}</span>
                </td>
                <td>
                  <span className="badge high">{stat.high_count}</span>
                </td>
                <td>
                  <span className="badge medium">{stat.medium_count}</span>
                </td>
                <td>
                  <span className="badge low">{stat.low_count}</span>
                </td>
                <td>{stat.open_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

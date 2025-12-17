import { useState, useEffect } from 'react'
import { getScanQueue } from '../api'

export default function ScanQueue() {
  const [queue, setQueue] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    loadQueue()
    const interval = setInterval(loadQueue, 10000) // Refresh every 10 seconds
    return () => clearInterval(interval)
  }, [filter])

  const loadQueue = async () => {
    try {
      setLoading(true)
      const response = await getScanQueue(filter || null)
      setQueue(response.data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2>📋 Scan Queue</h2>
      
      <div className="card">
        <div className="filter-bar" style={{ justifyContent: 'space-between' }}>
          <div>
            <label>Status</label>
            <select 
              value={filter} 
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="queued">⏳ Queued</option>
              <option value="processing">🔄 Processing</option>
              <option value="completed">✅ Completed</option>
              <option value="failed">❌ Failed</option>
            </select>
          </div>
          <button className="button secondary" onClick={loadQueue} style={{ alignSelf: 'flex-end' }}>
            🔄 Refresh
          </button>
        </div>

        {loading && <div className="loading">Loading queue...</div>}
        {error && <div className="error">{error}</div>}
        
        {!loading && !error && queue.length === 0 && (
          <div className="empty-state">No items in queue</div>
        )}
        
        {!loading && !error && queue.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Repository</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Attempts</th>
                <th>Queued At</th>
                <th>Started At</th>
                <th>Job Name</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((item) => (
                <tr key={item.id}>
                  <td style={{ fontWeight: 600 }}>
                    {item.repository_name || `#${item.repository_id}`}
                  </td>
                  <td>
                    <span className={`badge ${item.status}`}>
                      {item.status}
                    </span>
                  </td>
                  <td>
                    <span style={{ 
                      background: item.priority > 0 ? 'var(--warning-light)' : 'var(--gray-100)',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontWeight: 500,
                      fontSize: '0.85rem'
                    }}>
                      {item.priority}
                    </span>
                  </td>
                  <td>
                    <span style={{ color: item.attempts >= item.max_attempts ? 'var(--danger)' : 'var(--gray-600)' }}>
                      {item.attempts}/{item.max_attempts}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.85rem', color: 'var(--gray-600)' }}>
                    {new Date(item.queued_at).toLocaleString()}
                  </td>
                  <td style={{ fontSize: '0.85rem', color: 'var(--gray-600)' }}>
                    {item.started_at 
                      ? new Date(item.started_at).toLocaleString()
                      : '—'}
                  </td>
                  <td style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--gray-500)' }}>
                    {item.job_name || '—'}
                  </td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--danger)', maxWidth: '200px' }}>
                    {item.error_message || '—'}
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

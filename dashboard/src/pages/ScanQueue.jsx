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

  const getStatusColor = (status) => {
    switch (status) {
      case 'queued': return '#0969da'
      case 'processing': return '#fb8500'
      case 'completed': return '#1a7f37'
      case 'failed': return '#cf222e'
      default: return '#6e7781'
    }
  }

  return (
    <div>
      <h2>Scan Queue</h2>
      
      <div className="card">
        <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <label>Filter by status: </label>
            <select 
              value={filter} 
              onChange={(e) => setFilter(e.target.value)}
              style={{ marginLeft: '10px' }}
            >
              <option value="">All</option>
              <option value="queued">Queued</option>
              <option value="processing">Processing</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          <button className="button" onClick={loadQueue}>
            Refresh
          </button>
        </div>

        {loading && <div className="loading">Loading queue...</div>}
        {error && <div className="error">Error: {error}</div>}
        
        {!loading && !error && (
          <>
            {queue.length === 0 ? (
              <p style={{ textAlign: 'center', padding: '40px', color: '#6e7781' }}>
                No items in queue
              </p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Repository ID</th>
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
                      <td>{item.repository_id}</td>
                      <td>
                        <span 
                          className="badge" 
                          style={{ backgroundColor: getStatusColor(item.status) }}
                        >
                          {item.status}
                        </span>
                      </td>
                      <td>{item.priority}</td>
                      <td>
                        {item.attempts}/{item.max_attempts}
                      </td>
                      <td>
                        {new Date(item.queued_at).toLocaleString()}
                      </td>
                      <td>
                        {item.started_at 
                          ? new Date(item.started_at).toLocaleString()
                          : '-'}
                      </td>
                      <td style={{ fontSize: '11px' }}>
                        {item.job_name || '-'}
                      </td>
                      <td style={{ fontSize: '12px', color: '#d73a49', maxWidth: '200px' }}>
                        {item.error_message}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  )
}

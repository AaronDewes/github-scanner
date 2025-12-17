import { useState, useEffect } from 'react'
import { getRepositories } from '../api'

export default function Repositories() {
  const [repositories, setRepositories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [filter, setFilter] = useState('')

  const pageSize = 50

  useEffect(() => {
    loadRepositories()
  }, [page, filter])

  const loadRepositories = async () => {
    try {
      setLoading(true)
      const response = await getRepositories(page, pageSize, filter || null)
      setRepositories(response.data.data)
      setTotal(response.data.total)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <h2>📁 Repositories</h2>
      
      <div className="card">
        <div className="filter-bar">
          <div>
            <label>Status</label>
            <select 
              value={filter} 
              onChange={(e) => {
                setFilter(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Statuses</option>
              <option value="pending">⏳ Pending</option>
              <option value="scanning">🔄 Scanning</option>
              <option value="completed">✅ Completed</option>
              <option value="failed">❌ Failed</option>
            </select>
          </div>
        </div>

        {loading && <div className="loading">Loading repositories...</div>}
        {error && <div className="error">{error}</div>}
        
        {!loading && !error && repositories.length === 0 && (
          <div className="empty-state">No repositories found. Try scanning some repositories!</div>
        )}
        
        {!loading && !error && repositories.length > 0 && (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>Repository</th>
                  <th style={{ width: '120px' }}>Status</th>
                  <th style={{ width: '180px' }}>Last Scanned</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {repositories.map((repo) => (
                  <tr key={repo.id}>
                    <td>
                      <a 
                        href={repo.url} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        style={{ 
                          color: 'var(--primary)', 
                          textDecoration: 'none',
                          fontWeight: 500
                        }}
                      >
                        <strong style={{ color: 'var(--gray-900)' }}>{repo.owner}</strong>
                        <span style={{ color: 'var(--gray-400)' }}>/</span>
                        {repo.name}
                      </a>
                    </td>
                    <td>
                      <span className={`badge ${repo.scan_status}`}>
                        {repo.scan_status}
                      </span>
                    </td>
                    <td style={{ color: 'var(--gray-600)', fontSize: '0.875rem' }}>
                      {repo.last_scanned_at 
                        ? new Date(repo.last_scanned_at).toLocaleString()
                        : '—'}
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--danger)' }}>
                      {repo.scan_error || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="pagination">
              <button 
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                ← Previous
              </button>
              <span>
                Page {page} of {totalPages} ({total.toLocaleString()} total)
              </span>
              <button 
                onClick={() => setPage(p => p + 1)}
                disabled={page >= totalPages}
              >
                Next →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

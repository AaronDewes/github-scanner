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
      <h2>Repositories</h2>
      
      <div className="card">
        <div style={{ marginBottom: '20px' }}>
          <label>Filter by status: </label>
          <select 
            value={filter} 
            onChange={(e) => {
              setFilter(e.target.value)
              setPage(1)
            }}
            style={{ marginLeft: '10px' }}
          >
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="scanning">Scanning</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        {loading && <div className="loading">Loading repositories...</div>}
        {error && <div className="error">Error: {error}</div>}
        
        {!loading && !error && (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>Repository</th>
                  <th>Status</th>
                  <th>Last Scanned</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {repositories.map((repo) => (
                  <tr key={repo.id}>
                    <td>
                      <a href={repo.url} target="_blank" rel="noopener noreferrer">
                        {repo.owner}/{repo.name}
                      </a>
                    </td>
                    <td>
                      <span className={`badge ${repo.scan_status}`}>
                        {repo.scan_status}
                      </span>
                    </td>
                    <td>
                      {repo.last_scanned_at 
                        ? new Date(repo.last_scanned_at).toLocaleString()
                        : 'Never'}
                    </td>
                    <td style={{ fontSize: '12px', color: '#d73a49' }}>
                      {repo.scan_error}
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
                Previous
              </button>
              <span>
                Page {page} of {totalPages} ({total} total)
              </span>
              <button 
                onClick={() => setPage(p => p + 1)}
                disabled={page >= totalPages}
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

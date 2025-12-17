import { useState } from 'react'
import { triggerScan } from '../api'

export default function TriggerScan() {
  const [repoUrl, setRepoUrl] = useState('')
  const [priority, setPriority] = useState(0)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    try {
      setLoading(true)
      setError(null)
      setResult(null)
      
      const response = await triggerScan(repoUrl, parseInt(priority))
      setResult(response.data)
      setRepoUrl('')
      setPriority(0)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2>Trigger Repository Scan</h2>
      
      <div className="card">
        <p style={{ marginBottom: '20px', color: '#6e7781' }}>
          Manually trigger a security scan for a specific GitHub repository. 
          The repository will be added to the scan queue and processed by a worker.
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Repository URL</label>
            <input
              type="text"
              className="input"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repository"
              required
            />
            <small style={{ color: '#6e7781' }}>
              Enter the full GitHub repository URL
            </small>
          </div>

          <div className="form-group">
            <label>Priority</label>
            <input
              type="number"
              className="input"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              min="0"
              max="100"
            />
            <small style={{ color: '#6e7781' }}>
              Higher priority scans are processed first (0-100, default: 0)
            </small>
          </div>

          <button 
            type="submit" 
            className="button" 
            disabled={loading || !repoUrl}
          >
            {loading ? 'Submitting...' : 'Trigger Scan'}
          </button>
        </form>

        {error && (
          <div className="error" style={{ marginTop: '20px' }}>
            Error: {error}
          </div>
        )}

        {result && (
          <div 
            style={{ 
              marginTop: '20px', 
              padding: '15px', 
              backgroundColor: '#dafbe1', 
              border: '1px solid #1a7f37',
              borderRadius: '6px',
              color: '#1a7f37'
            }}
          >
            <h3>✓ Scan Queued Successfully</h3>
            <p><strong>Message:</strong> {result.message}</p>
            <p><strong>Repository ID:</strong> {result.repository_id}</p>
            <p><strong>Scan Queue ID:</strong> {result.scan_queue_id}</p>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Examples</h3>
        <ul style={{ marginLeft: '20px', color: '#6e7781' }}>
          <li style={{ marginBottom: '10px' }}>
            <code>https://github.com/actions/checkout</code> - Popular GitHub Action
          </li>
          <li style={{ marginBottom: '10px' }}>
            <code>https://github.com/actions/setup-python</code> - Python setup action
          </li>
          <li style={{ marginBottom: '10px' }}>
            <code>https://github.com/owner/repo</code> - Any public repository
          </li>
        </ul>
      </div>
    </div>
  )
}

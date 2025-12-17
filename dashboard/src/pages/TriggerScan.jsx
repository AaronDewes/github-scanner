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

  const exampleRepos = [
    { url: 'https://github.com/actions/checkout', name: 'actions/checkout', desc: 'Popular GitHub Action' },
    { url: 'https://github.com/actions/setup-python', name: 'actions/setup-python', desc: 'Python setup action' },
    { url: 'https://github.com/actions/setup-node', name: 'actions/setup-node', desc: 'Node.js setup action' },
  ]

  return (
    <div>
      <h2>🔍 Trigger Repository Scan</h2>
      
      <div className="card">
        <p style={{ marginBottom: '24px', color: 'var(--gray-600)', lineHeight: 1.7 }}>
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
            <small style={{ color: 'var(--gray-500)', fontSize: '0.85rem' }}>
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
              style={{ maxWidth: '150px' }}
            />
            <small style={{ color: 'var(--gray-500)', fontSize: '0.85rem' }}>
              Higher priority scans are processed first (0-100, default: 0)
            </small>
          </div>

          <button 
            type="submit" 
            className="button" 
            disabled={loading || !repoUrl}
          >
            {loading ? '⏳ Submitting...' : '🚀 Trigger Scan'}
          </button>
        </form>

        {error && (
          <div className="error" style={{ marginTop: '20px' }}>
            {error}
          </div>
        )}

        {result && (
          <div 
            style={{ 
              marginTop: '24px', 
              padding: '20px', 
              background: 'var(--success-light)', 
              border: '1px solid #6ee7b7',
              borderRadius: 'var(--radius)',
              color: '#047857'
            }}
          >
            <h3 style={{ marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>✅</span> Scan Queued Successfully
            </h3>
            <p style={{ marginBottom: '8px' }}><strong>Message:</strong> {result.message}</p>
            <p style={{ marginBottom: '8px' }}><strong>Repository ID:</strong> #{result.repository_id}</p>
            <p><strong>Scan Queue ID:</strong> #{result.scan_queue_id}</p>
          </div>
        )}
      </div>

      <div className="card">
        <h3>📚 Quick Examples</h3>
        <p style={{ color: 'var(--gray-500)', marginBottom: '16px', fontSize: '0.9rem' }}>
          Click on any example to populate the form:
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {exampleRepos.map((repo) => (
            <div 
              key={repo.url}
              onClick={() => setRepoUrl(repo.url)}
              style={{ 
                padding: '14px 18px',
                background: 'var(--gray-50)',
                border: '1px solid var(--gray-200)',
                borderRadius: 'var(--radius)',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.background = 'var(--primary-light)'
                e.currentTarget.style.borderColor = 'var(--primary)'
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.background = 'var(--gray-50)'
                e.currentTarget.style.borderColor = 'var(--gray-200)'
              }}
            >
              <div>
                <code style={{ 
                  color: 'var(--primary)', 
                  fontWeight: 500,
                  fontSize: '0.9rem'
                }}>
                  {repo.name}
                </code>
                <span style={{ color: 'var(--gray-500)', marginLeft: '12px', fontSize: '0.85rem' }}>
                  — {repo.desc}
                </span>
              </div>
              <span style={{ color: 'var(--gray-400)', fontSize: '0.8rem' }}>Click to use →</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

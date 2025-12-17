import { useState, useEffect } from 'react'
import { getVulnerabilities, getVulnerabilityFilters, updateVulnerabilityAnalysis, markVulnerabilityFileSafe } from '../api'

export default function Vulnerabilities() {
  const [vulnerabilities, setVulnerabilities] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [filters, setFilters] = useState({
    severity: '',
    status: '',
    org: '',
    repo: ''
  })
  const [filterOptions, setFilterOptions] = useState({
    organizations: [],
    repositories: []
  })
  const [selectedVuln, setSelectedVuln] = useState(null)
  const [analysisForm, setAnalysisForm] = useState({
    status: 'open',
    manual_analysis: '',
    analyzed_by: ''
  })

  const pageSize = 50

  useEffect(() => {
    loadFilterOptions()
  }, [])

  useEffect(() => {
    loadVulnerabilities()
  }, [page, filters])

  const loadFilterOptions = async () => {
    try {
      const response = await getVulnerabilityFilters()
      setFilterOptions(response.data)
    } catch (err) {
      console.error('Failed to load filter options:', err)
    }
  }

  const loadVulnerabilities = async () => {
    try {
      setLoading(true)
      const cleanFilters = {}
      if (filters.severity) cleanFilters.severity = filters.severity
      if (filters.status) cleanFilters.status = filters.status
      if (filters.org) cleanFilters.org = filters.org
      if (filters.repo) cleanFilters.repo = filters.repo
      
      const response = await getVulnerabilities(page, pageSize, cleanFilters)
      setVulnerabilities(response.data.data)
      setTotal(response.data.total)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Get repositories filtered by selected org
  const filteredRepos = filters.org 
    ? filterOptions.repositories.filter(r => r.owner === filters.org)
    : filterOptions.repositories

  const handleUpdateAnalysis = async (e) => {
    e.preventDefault()
    
    try {
      await updateVulnerabilityAnalysis(selectedVuln.id, analysisForm)
      setSelectedVuln(null)
      loadVulnerabilities()
    } catch (err) {
      alert('Failed to update analysis: ' + err.message)
    }
  }

  const handleMarkFileSafe = async () => {
    if (!window.confirm('Mark this file as safe globally? This will ignore all vulnerabilities in this file across ALL repositories and branches.')) {
      return
    }
    
    try {
      const reason = prompt('Reason for marking safe (optional):')
      const markedBy = prompt('Your name (optional):')
      await markVulnerabilityFileSafe(selectedVuln.id, reason, markedBy)
      alert('File marked as safe globally. All matching vulnerabilities have been ignored.')
      setSelectedVuln(null)
      loadVulnerabilities()
    } catch (err) {
      alert('Failed to mark file safe: ' + err.message)
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <h2>Vulnerabilities</h2>
      
      <div className="card">
        <div style={{ display: 'flex', gap: '20px', marginBottom: '20px', flexWrap: 'wrap' }}>
          <div>
            <label>Organization: </label>
            <select 
              value={filters.org} 
              onChange={(e) => {
                setFilters({ ...filters, org: e.target.value, repo: '' })
                setPage(1)
              }}
            >
              <option value="">All Organizations</option>
              {filterOptions.organizations.map(org => (
                <option key={org} value={org}>{org}</option>
              ))}
            </select>
          </div>
          <div>
            <label>Repository: </label>
            <select 
              value={filters.repo} 
              onChange={(e) => {
                setFilters({ ...filters, repo: e.target.value })
                setPage(1)
              }}
            >
              <option value="">All Repositories</option>
              {filteredRepos.map(repo => (
                <option key={`${repo.owner}/${repo.name}`} value={repo.name}>
                  {filters.org ? repo.name : `${repo.owner}/${repo.name}`}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>Severity: </label>
            <select 
              value={filters.severity} 
              onChange={(e) => {
                setFilters({ ...filters, severity: e.target.value })
                setPage(1)
              }}
            >
              <option value="">All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="info">Info</option>
            </select>
          </div>
          <div>
            <label>Status: </label>
            <select 
              value={filters.status} 
              onChange={(e) => {
                setFilters({ ...filters, status: e.target.value })
                setPage(1)
              }}
            >
              <option value="">All</option>
              <option value="open">Open</option>
              <option value="confirmed">Confirmed</option>
              <option value="false_positive">False Positive</option>
              <option value="fixed">Fixed</option>
              <option value="ignored">Ignored</option>
            </select>
          </div>
        </div>

        {loading && <div className="loading">Loading vulnerabilities...</div>}
        {error && <div className="error">Error: {error}</div>}
        
        {!loading && !error && (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Repository</th>
                  <th>Title</th>
                  <th>File</th>
                  <th>Status</th>
                  <th>Detected</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {vulnerabilities.map((vuln) => (
                  <tr key={vuln.id}>
                    <td>
                      <span className={`badge ${vuln.severity}`}>
                        {vuln.severity}
                      </span>
                    </td>
                    <td style={{ fontSize: '12px' }}>
                      {vuln.repo_owner}/{vuln.repo_name}
                    </td>
                    <td>{vuln.title}</td>
                    <td style={{ fontSize: '12px' }}>{vuln.file_path}</td>
                    <td>
                      <span className={`badge ${vuln.status}`}>
                        {vuln.status}
                      </span>
                    </td>
                    <td>
                      {new Date(vuln.detected_at).toLocaleDateString()}
                    </td>
                    <td>
                      <button 
                        className="button"
                        style={{ padding: '5px 10px', fontSize: '12px' }}
                        onClick={() => {
                          setSelectedVuln(vuln)
                          setAnalysisForm({
                            status: vuln.status,
                            manual_analysis: vuln.manual_analysis || '',
                            analyzed_by: vuln.analyzed_by || ''
                          })
                        }}
                      >
                        Analyze
                      </button>
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

      {selectedVuln && (
        <div className="modal" onClick={() => setSelectedVuln(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setSelectedVuln(null)}>
              ×
            </button>
            <h2>Vulnerability Analysis</h2>
            
            <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f6f8fa', borderRadius: '6px' }}>
              <h3>{selectedVuln.title}</h3>
              <p><strong>Type:</strong> {selectedVuln.vulnerability_type}</p>
              <p><strong>File:</strong> {selectedVuln.file_path}</p>
              {selectedVuln.line_number && <p><strong>Line:</strong> {selectedVuln.line_number}</p>}
              {selectedVuln.description && (
                <p><strong>Description:</strong> {selectedVuln.description}</p>
              )}
              {selectedVuln.code_snippet && (
                <pre style={{ background: '#fff', padding: '10px', borderRadius: '4px', overflow: 'auto' }}>
                  <code>{selectedVuln.code_snippet}</code>
                </pre>
              )}
              {selectedVuln.recommendation && (
                <p><strong>Recommendation:</strong> {selectedVuln.recommendation}</p>
              )}
            </div>

            <form onSubmit={handleUpdateAnalysis}>
              <div className="form-group">
                <label>Status</label>
                <select 
                  value={analysisForm.status}
                  onChange={(e) => setAnalysisForm({ ...analysisForm, status: e.target.value })}
                  required
                >
                  <option value="open">Open</option>
                  <option value="confirmed">Confirmed</option>
                  <option value="false_positive">False Positive</option>
                  <option value="fixed">Fixed</option>
                  <option value="ignored">Ignored</option>
                </select>
              </div>

              <div className="form-group">
                <label>Analysis Notes</label>
                <textarea
                  value={analysisForm.manual_analysis}
                  onChange={(e) => setAnalysisForm({ ...analysisForm, manual_analysis: e.target.value })}
                  placeholder="Add your analysis notes here..."
                />
              </div>

              <div className="form-group">
                <label>Analyzed By</label>
                <input
                  type="text"
                  className="input"
                  value={analysisForm.analyzed_by}
                  onChange={(e) => setAnalysisForm({ ...analysisForm, analyzed_by: e.target.value })}
                  placeholder="Your name"
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
                <button type="submit" className="button">
                  Update Analysis
                </button>
                <button 
                  type="button" 
                  className="button" 
                  style={{ backgroundColor: '#6c757d' }}
                  onClick={handleMarkFileSafe}
                >
                  Mark File Safe (Global)
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

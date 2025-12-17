import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const getHealth = () => api.get('/health')

export const getStats = () => api.get('/stats')

export const getStatsSummary = () => api.get('/stats/summary')

export const getRepositories = (page = 1, pageSize = 50, status = null) => {
  const params = { page, page_size: pageSize }
  if (status) params.status = status
  return api.get('/repositories', { params })
}

export const getRepository = (id) => api.get(`/repositories/${id}`)

export const getVulnerabilities = (page = 1, pageSize = 50, filters = {}) => {
  const params = { page, page_size: pageSize, ...filters }
  return api.get('/vulnerabilities', { params })
}

export const getVulnerabilityFilters = () => api.get('/vulnerabilities/filters')

export const getVulnerability = (id) => api.get(`/vulnerabilities/${id}`)

export const updateVulnerabilityAnalysis = (id, data) => 
  api.put(`/vulnerabilities/${id}/analysis`, data)

export const getScanQueue = (status = null) => {
  const params = status ? { status } : {}
  return api.get('/queue', { params })
}

export const triggerScan = (repoUrl, priority = 0) => 
  api.post('/scan', { repo_url: repoUrl, priority })

// Safe Files API
export const getSafeFiles = () => api.get('/safe-files')

export const markFileSafe = (filePath, fileHash = null, reason = null, markedBy = null) => {
  const params = { file_path: filePath }
  if (fileHash) params.file_hash = fileHash
  if (reason) params.reason = reason
  if (markedBy) params.marked_by = markedBy
  return api.post('/safe-files', null, { params })
}

export const removeSafeFile = (id) => api.delete(`/safe-files/${id}`)

export const markVulnerabilityFileSafe = (vulnId, reason = null, markedBy = null) => {
  const params = {}
  if (reason) params.reason = reason
  if (markedBy) params.marked_by = markedBy
  return api.post(`/vulnerabilities/${vulnId}/mark-file-safe`, null, { params })
}

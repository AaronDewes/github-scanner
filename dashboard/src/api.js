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

export const getVulnerability = (id) => api.get(`/vulnerabilities/${id}`)

export const updateVulnerabilityAnalysis = (id, data) => 
  api.put(`/vulnerabilities/${id}/analysis`, data)

export const getScanQueue = (status = null) => {
  const params = status ? { status } : {}
  return api.get('/queue', { params })
}

export const triggerScan = (repoUrl, priority = 0) => 
  api.post('/scan', { repo_url: repoUrl, priority })

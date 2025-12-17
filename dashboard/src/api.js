import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const getHealth = () => api.get('/health')

export const getStats = () => api.get(`${API_URL}/stats`)

export const getRepositories = (page = 1, pageSize = 50, status = null) => {
  const params = { page, page_size: pageSize }
  if (status) params.status = status
  return api.get(`${API_URL}/repositories`, { params })
}

export const getRepository = (id) => api.get(`${API_URL}/repositories/${id}`)

export const getVulnerabilities = (page = 1, pageSize = 50, filters = {}) => {
  const params = { page, page_size: pageSize, ...filters }
  return api.get(`${API_URL}/vulnerabilities`, { params })
}

export const getVulnerability = (id) => api.get(`${API_URL}/vulnerabilities/${id}`)

export const updateVulnerabilityAnalysis = (id, data) => 
  api.put(`${API_URL}/vulnerabilities/${id}/analysis`, data)

export const getScanQueue = (status = null) => {
  const params = status ? { status } : {}
  return api.get(`${API_URL}/queue`, { params })
}

export const triggerScan = (repoUrl, priority = 0) => 
  api.post(`${API_URL}/scan`, { repo_url: repoUrl, priority })

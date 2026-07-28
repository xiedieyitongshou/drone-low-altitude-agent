import axios from 'axios'
import { getStoredAccessToken } from '../auth/tokenStorage'

const apiTimeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 60000)

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  timeout: Number.isFinite(apiTimeoutMs) && apiTimeoutMs > 0 ? apiTimeoutMs : 60000,
})

apiClient.interceptors.request.use((config) => {
  const token = getStoredAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

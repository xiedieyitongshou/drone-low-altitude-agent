import axios from 'axios'

const apiTimeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 60000)

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  timeout: Number.isFinite(apiTimeoutMs) && apiTimeoutMs > 0 ? apiTimeoutMs : 60000,
})

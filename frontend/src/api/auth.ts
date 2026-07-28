import { apiClient } from './client'
import type { LoginRequest, RegisterRequest, TokenResponse, User } from '../types/auth'

export async function registerUser(payload: RegisterRequest) {
  const response = await apiClient.post<User>('/auth/register', payload)
  return response.data
}

export async function loginUser(payload: LoginRequest) {
  const response = await apiClient.post<TokenResponse>('/auth/login', payload)
  return response.data
}

export async function getCurrentUser() {
  const response = await apiClient.get<User>('/auth/me')
  return response.data
}

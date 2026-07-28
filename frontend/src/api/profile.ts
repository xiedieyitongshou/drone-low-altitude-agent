import { apiClient } from './client'
import type { UserProfile, UserProfileUpdateRequest } from '../types/profile'

export async function getMyProfile() {
  const response = await apiClient.get<UserProfile>('/users/me/profile')
  return response.data
}

export async function updateMyProfile(payload: UserProfileUpdateRequest) {
  const response = await apiClient.patch<UserProfile>('/users/me/profile', payload)
  return response.data
}

import { apiClient } from './client'
import type {
  AdminConversationDetail,
  AdminConversationListResponse,
  AdminTaskStats,
  AdminUser,
  AdminUserListResponse,
} from '../types/admin'
import type { UserRole } from '../types/auth'

type ListUsersParams = {
  page?: number
  page_size?: number
  username?: string
  role?: UserRole | ''
  is_active?: boolean | ''
}

type ListConversationsParams = {
  page?: number
  page_size?: number
  user_id?: string
  session_id?: string
  intent?: string
  parser_source?: string
  success?: boolean | ''
  keyword?: string
  created_from?: string
  created_to?: string
}

export async function getAdminTaskStats() {
  const response = await apiClient.get<AdminTaskStats>('/admin/stats/tasks')
  return response.data
}

export async function listAdminUsers(params: ListUsersParams = {}) {
  const response = await apiClient.get<AdminUserListResponse>('/admin/users', {
    params: cleanParams(params),
  })
  return response.data
}

export async function updateAdminUserStatus(userId: string, isActive: boolean) {
  const response = await apiClient.patch<AdminUser>(`/admin/users/${userId}/status`, {
    is_active: isActive,
  })
  return response.data
}

export async function updateAdminUserRole(userId: string, role: UserRole) {
  const response = await apiClient.patch<AdminUser>(`/admin/users/${userId}/role`, { role })
  return response.data
}

export async function listAdminConversations(params: ListConversationsParams = {}) {
  const response = await apiClient.get<AdminConversationListResponse>('/admin/conversations', {
    params: cleanParams(params),
  })
  return response.data
}

export async function getAdminConversationDetail(conversationId: string) {
  const response = await apiClient.get<AdminConversationDetail>(
    `/admin/conversations/${conversationId}`,
  )
  return response.data
}

function cleanParams<T extends Record<string, unknown>>(params: T) {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== '' && value !== undefined && value !== null),
  )
}

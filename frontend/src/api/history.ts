import { apiClient } from './client'
import type {
  ConversationDetailResponse,
  ConversationListParams,
  ConversationListResponse,
  CruiseHistoryResponse,
  UnifiedBusinessResponse,
} from '../types/history'

export async function getCruiseHistory(requestId: string) {
  const response = await apiClient.get<CruiseHistoryResponse>(
    `/cruise/history/${encodeURIComponent(requestId)}`,
  )
  return response.data
}

export async function getCruiseHistoryComposed(requestId: string) {
  const response = await apiClient.get<UnifiedBusinessResponse>(
    `/cruise/history/${encodeURIComponent(requestId)}/composed`,
  )
  return response.data
}

export async function listConversations(params: ConversationListParams = {}) {
  const response = await apiClient.get<ConversationListResponse>('/agent/conversations', {
    params,
  })
  return response.data
}

export async function getConversationDetail(conversationId: string) {
  const response = await apiClient.get<ConversationDetailResponse>(
    `/agent/conversations/${encodeURIComponent(conversationId)}`,
  )
  return response.data
}

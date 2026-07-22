import { apiClient } from './client'
import type { CruiseHistoryResponse, UnifiedBusinessResponse } from '../types/history'

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

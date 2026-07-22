import { apiClient } from './client'
import type { AgentQueryRequest, AgentQueryResponse } from '../types/agent'

export async function queryAgent(payload: AgentQueryRequest) {
  const response = await apiClient.post<AgentQueryResponse>('/agent/query', payload)
  return response.data
}

import { apiClient } from './client'
import type { AgentQueryRequest, AgentQueryResponse } from '../types/agent'

export async function queryAgent(payload: AgentQueryRequest, idempotencyKey?: string) {
  const response = await apiClient.post<AgentQueryResponse>('/agent/query', payload, {
    headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
  })
  return response.data
}

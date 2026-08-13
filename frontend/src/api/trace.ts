import { apiClient } from './client'
import type { AgentTraceDetailResponse } from '../types/trace'

export async function getAgentTrace(traceId: string) {
  const response = await apiClient.get<AgentTraceDetailResponse>(
    `/agent/traces/${encodeURIComponent(traceId)}`,
  )
  return response.data
}

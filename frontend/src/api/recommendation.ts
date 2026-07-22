import { apiClient } from './client'
import type {
  RecommendationRequest,
  RecommendationResponse,
} from '../types/recommendation'

export async function recommendExecutionWindows(payload: RecommendationRequest) {
  const response = await apiClient.post<RecommendationResponse>(
    '/cruise/recommend',
    payload,
  )
  return response.data
}

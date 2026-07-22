import { apiClient } from './client'
import type {
  MultiLocationComparisonRequest,
  MultiLocationComparisonResponse,
} from '../types/comparison'

export async function compareCruiseLocations(
  payload: MultiLocationComparisonRequest,
) {
  const response = await apiClient.post<MultiLocationComparisonResponse>(
    '/cruise/compare',
    payload,
  )
  return response.data
}

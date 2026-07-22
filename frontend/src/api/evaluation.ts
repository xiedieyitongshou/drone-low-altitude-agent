import { apiClient } from './client'
import type {
  CruiseAssessmentResponse,
  CruiseEvaluateRequest,
} from '../types/evaluation'

export async function evaluateCruise(payload: CruiseEvaluateRequest) {
  const response = await apiClient.post<CruiseAssessmentResponse>(
    '/cruise/evaluate',
    payload,
  )
  return response.data
}

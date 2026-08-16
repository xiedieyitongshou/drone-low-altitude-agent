import { apiClient } from './client'
import type {
  MissionTaskCreateRequest,
  MissionTaskDetailResponse,
  MissionTaskListParams,
  MissionTaskListResponse,
  MissionTaskRecommendRequest,
  MissionTaskResponse,
  MissionTaskSelectWindowRequest,
  MissionTaskStatus,
  MissionTaskUpdateRequest,
} from '../types/missionTask'
import type { CruiseAssessmentResponse } from '../types/evaluation'
import type { RecommendationResponse } from '../types/recommendation'

export async function listMissionTasks(params: MissionTaskListParams = {}) {
  const response = await apiClient.get<MissionTaskListResponse>('/tasks', { params })
  return response.data
}

export async function createMissionTask(payload: MissionTaskCreateRequest) {
  const response = await apiClient.post<MissionTaskResponse>('/tasks', payload)
  return response.data
}

export async function getMissionTask(taskId: string) {
  const response = await apiClient.get<MissionTaskDetailResponse>(
    `/tasks/${encodeURIComponent(taskId)}`,
  )
  return response.data
}

export async function updateMissionTask(taskId: string, payload: MissionTaskUpdateRequest) {
  const response = await apiClient.patch<MissionTaskResponse>(
    `/tasks/${encodeURIComponent(taskId)}`,
    payload,
  )
  return response.data
}

export async function updateMissionTaskStatus(taskId: string, status: MissionTaskStatus) {
  const response = await apiClient.patch<MissionTaskResponse>(
    `/tasks/${encodeURIComponent(taskId)}/status`,
    { status },
  )
  return response.data
}

export async function evaluateMissionTask(taskId: string) {
  const response = await apiClient.post<CruiseAssessmentResponse>(
    `/tasks/${encodeURIComponent(taskId)}/evaluate`,
  )
  return response.data
}

export async function recommendMissionTaskWindows(
  taskId: string,
  payload: MissionTaskRecommendRequest = {},
) {
  const response = await apiClient.post<RecommendationResponse>(
    `/tasks/${encodeURIComponent(taskId)}/recommend`,
    payload,
  )
  return response.data
}

export async function selectMissionTaskWindow(
  taskId: string,
  payload: MissionTaskSelectWindowRequest,
) {
  const response = await apiClient.post<MissionTaskResponse>(
    `/tasks/${encodeURIComponent(taskId)}/select-window`,
    payload,
  )
  return response.data
}

export async function preflightCheckMissionTask(taskId: string) {
  const response = await apiClient.post<CruiseAssessmentResponse>(
    `/tasks/${encodeURIComponent(taskId)}/preflight-check`,
  )
  return response.data
}

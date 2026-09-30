/**
 * 行程 API
 */
import { request } from './index'

export interface Trip {
  id: string
  user_id: string
  title: string
  destination: string
  start_date: string
  end_date: string
  budget: number
  travelers: number
  status: string
  requirements: Record<string, any>
  generated_plan?: Record<string, any>
  created_at: string
  updated_at?: string
}

export interface TripCreatePayload {
  title: string
  destination: string
  start_date: string
  end_date: string
  budget: number
  travelers: number
  requirements?: Record<string, any>
}

/** 由 AI 行程保存为「我的行程」 */
export interface TripFromPlanPayload extends TripCreatePayload {
  /** AI 生成的 Markdown 行程正文 */
  content: string
  weather_info?: Record<string, any> | null
  source_message?: string
}

/** 行程字段推断请求（用于保存弹窗预填） */
export interface PlanExtractPayload {
  content: string
  weather_info?: Record<string, any> | null
  tool_calls?: Array<{ name: string; args: Record<string, any> }>
  user_message?: string
}

/** 行程字段推断结果 */
export interface PlanExtractResult {
  title: string
  destination: string
  start_date: string
  end_date: string
  budget: number
  travelers: number
  days_count: number
}

export const tripApi = {
  list: (params?: { status_filter?: string; limit?: number; offset?: number }) => {
    return request.get<Trip[]>('/api/v1/trips', { params })
  },

  create: (data: TripCreatePayload) => {
    return request.post<Trip>('/api/v1/trips', data)
  },

  /** 推断「保存到我的行程」弹窗的预填字段（不落库） */
  extractPlan: (data: PlanExtractPayload) => {
    return request.post<PlanExtractResult>('/api/v1/trips/plan/extract', data)
  },

  /** 保存 AI 行程到「我的行程」（含生成的规划正文） */
  createFromPlan: (data: TripFromPlanPayload) => {
    return request.post<Trip>('/api/v1/trips/from-plan', data)
  },

  detail: (tripId: string) => {
    return request.get<Trip>(`/api/v1/trips/${tripId}`)
  },

  update: (tripId: string, data: Partial<TripCreatePayload> & { status?: string }) => {
    return request.put<Trip>(`/api/v1/trips/${tripId}`, data)
  },

  remove: (tripId: string) => {
    return request.delete(`/api/v1/trips/${tripId}`)
  },
}

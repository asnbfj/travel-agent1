/**
 * Agent 对话 API
 */
import { request } from './index'
import http from './index'

export interface AgentMessageRequest {
  message: string
  context?: Record<string, any>
}

export interface ToolCall {
  name: string
  args: Record<string, any>
}

export interface AgentMessageResponse {
  message: string
  intent?: string
  suggested_actions: string[]
  itinerary?: {
    content: string
    spots_used: string[]
  } | null
  weather_info?: {
    city: string
    forecasts: Array<{
      date: string
      weekday: string
      weather: string
      icon: string
      temp_high: number | null
      temp_low: number | null
      wind?: string
      pm25?: number | null
    }>
    tips: string
    /** 数据来源（天气为高德地图天气接口） */
    source?: string
    /** 预报发布时间 */
    report_time?: string
    /** 联网检索到的原始来源链接（景点/酒店用） */
    sources?: Array<{ title: string; url: string; published_date?: string }>
  } | null
  /** 本次实际调用的线上工具（高德地图 / 博查 AI 搜索） */
  tool_calls?: ToolCall[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  metadata?: Record<string, any>
}

export interface AgentPdfExportRequest {
  /** 行程 Markdown 正文（即 AI 回复内容） */
  content: string
  title?: string
  destination?: string
  weather_info?: Record<string, any>
}

/** 从 Content-Disposition 里解析文件名（优先 RFC 5987 的 filename*） */
function parseFilename(disposition?: string): string {
  if (!disposition) return 'TravelAI-行程.pdf'
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ''))
    } catch {
      /* 解码失败则退回下面的 filename= */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition)
  return plain ? plain[1].trim() : 'TravelAI-行程.pdf'
}

/**
 * 导出行程 PDF
 *
 * 这里直接用 axios 实例（而非 `request` 封装），因为需要读取响应头里的
 * Content-Disposition 才能拿到服务端生成的、含中文的文件名。
 */
export async function exportItineraryPdf(
  data: AgentPdfExportRequest,
): Promise<{ blob: Blob; filename: string }> {
  const res = await http.post<Blob>('/api/v1/agent/export/pdf', data, {
    responseType: 'blob',
  })
  return {
    blob: res.data,
    filename: parseFilename(res.headers?.['content-disposition'] as string | undefined),
  }
}

/** 把后端返回的错误（可能是 JSON，也可能是二进制流）转成可读文案 */
export async function readExportError(error: any): Promise<string> {
  const data = error?.response?.data
  if (data instanceof Blob) {
    try {
      const text = await data.text()
      const parsed = JSON.parse(text)
      return parsed?.detail || text
    } catch {
      return '生成 PDF 失败，请重试'
    }
  }
  return data?.detail || error?.message || '生成 PDF 失败，请重试'
}

export const agentApi = {
  /**
   * 发送消息给 Agent
   */
  chat: (data: AgentMessageRequest) => {
    return request.post<AgentMessageResponse>('/api/v1/agent/chat', data)
  },

  /**
   * 获取对话历史
   */
  getHistory: (params?: { limit?: number; offset?: number }) => {
    return request.get<{
      messages: ChatMessage[]
      total: number
      has_more: boolean
    }>('/api/v1/agent/history', { params })
  },

  /**
   * 清除对话历史
   */
  clearHistory: () => {
    return request.delete('/api/v1/agent/history')
  },
}

/**
 * Agent 对话 API
 */
import { request } from './index'
import http from './index'

export interface AgentMessageRequest {
  message: string
  context?: Record<string, any>
  /** 会话 ID；不传表示开一段新会话，服务端会生成并回传 */
  conversation_id?: string | null
}

export interface ToolCall {
  name: string
  args: Record<string, any>
}

/** 天气卡片数据（来自高德地图天气接口） */
export interface WeatherInfo {
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
}

export interface AgentMessageResponse {
  message: string
  intent?: string
  suggested_actions: string[]
  itinerary?: {
    content: string
    spots_used: string[]
  } | null
  weather_info?: WeatherInfo | null
  /** 本次实际调用的线上工具（高德地图 / 博查 AI 搜索） */
  tool_calls?: ToolCall[]
  /** 本次回复所属会话 ID（新建会话时由服务端生成） */
  conversation_id?: string | null
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  metadata?: Record<string, any>
  /** 以下字段由服务端从 metadata 摊平，历史消息也能还原工具标签与天气卡片 */
  tool_calls?: ToolCall[]
  weather_info?: WeatherInfo | null
  suggested_actions?: string[]
  intent?: string | null
}

/** 侧边栏会话列表项 */
export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
  preview: string
}

export interface ConversationDetail {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: ChatMessage[]
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

/** 执行过程事件（SSE 推送） */
export interface ProgressEvent {
  type: 'stage' | 'tool_start' | 'tool_end' | 'retry'
  /** stage：阶段文案与标识 */
  text?: string
  key?: string
  /** 工具事件：工具名与展示名 */
  name?: string
  label?: string
  source?: string
  summary?: string
  call_id?: string
  /** tool_end：是否成功、耗时、失败原因 */
  ok?: boolean
  duration_ms?: number
  error?: string
  /** retry：第几次重试 / 共几次 / 等待秒数 / 原因 */
  attempt?: number
  total?: number
  delay?: number
  reason?: string
}

/** SSE 收尾帧的载荷 */
export interface ChatStreamResult {
  conversation_id: string
  message: string
  intent?: string | null
  weather_info?: WeatherInfo | null
  tool_calls?: ToolCall[]
  suggested_actions: string[]
}

/**
 * 流式接口不可用（后端未升级 / 反向代理不支持 SSE）
 *
 * 调用方据此回退到非流式 `/chat`，避免整个功能不可用。
 */
export class ChatStreamUnavailableError extends Error {}

/**
 * SSE 帧：载荷字段是四类进度事件与收尾帧的并集
 *
 * 这里刻意把 `type` 放宽成 `string`——数据来自网络、不可信，
 * 必须先收下来再按 `type` 分派，而不能假设它一定落在已知取值里。
 */
type StreamFrame = Omit<ProgressEvent, 'type'> &
  Partial<ChatStreamResult> & { type: string }

/** 解析缓冲区里已经完整的 SSE 帧，并返回剩余的不完整部分 */
function splitSseFrames(buffer: string): { frames: string[]; rest: string } {
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''
  return { frames: parts, rest }
}

/** 从一帧里取出 `data:` 载荷 */
function frameData(frame: string): string {
  if (!frame.trim()) return ''
  return frame
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')
}

/**
 * 发送消息并接收执行过程推送
 *
 * 优先走 SSE（能实时看到「执行到哪一步」）；若流式通道不可用，
 * 自动回退到一次性 `/chat`，此时不会有过程事件，只有最终结果。
 */
export async function sendChatMessage(
  payload: AgentMessageRequest,
  handlers: { onProgress?: (event: ProgressEvent) => void } = {},
): Promise<ChatStreamResult> {
  try {
    return await streamChatMessage(payload, handlers)
  } catch (error) {
    if (!(error instanceof ChatStreamUnavailableError)) throw error
    // 流式不可用：退回非流式，功能不降级到「不能用」
    const plain = await agentApi.chat(payload)
    return {
      conversation_id: plain.conversation_id || '',
      message: plain.message,
      intent: plain.intent,
      weather_info: plain.weather_info ?? null,
      tool_calls: plain.tool_calls ?? [],
      suggested_actions: plain.suggested_actions ?? [],
    }
  }
}

/** 走 SSE 的实现；通道不可用时抛 ChatStreamUnavailableError */
async function streamChatMessage(
  payload: AgentMessageRequest,
  handlers: { onProgress?: (event: ProgressEvent) => void },
): Promise<ChatStreamResult> {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const token = localStorage.getItem('token')

  let response: Response
  try {
    response = await fetch(`${base}/api/v1/agent/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    })
  } catch (error) {
    // 网络层失败：可能是后端没起或代理不支持，交给上层回退
    throw new ChatStreamUnavailableError('无法建立流式连接')
  }

  // 404 = 后端没有这个端点（未升级）；401 等业务错误应原样抛出
  if (response.status === 404) {
    throw new ChatStreamUnavailableError('后端未提供流式接口')
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response)
    throw new Error(detail)
  }
  if (!response.body) {
    throw new ChatStreamUnavailableError('响应不支持流式读取')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: ChatStreamResult | null = null
  let sawAnyFrame = false
  let streamError = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const { frames, rest } = splitSseFrames(buffer)
      buffer = rest

      for (const frame of frames) {
        const raw = frameData(frame)
        if (!raw) continue
        sawAnyFrame = true

        let event: StreamFrame
        try {
          event = JSON.parse(raw)
        } catch {
          continue // 忽略无法解析的帧，不影响后续事件
        }

        if (event.type === 'done') {
          result = {
            conversation_id: event.conversation_id || '',
            message: event.message || '',
            intent: event.intent,
            weather_info: event.weather_info ?? null,
            tool_calls: event.tool_calls ?? [],
            suggested_actions: event.suggested_actions ?? [],
          }
        } else if (event.type === 'error') {
          streamError = event.text || '处理失败'
          handlers.onProgress?.({ type: 'stage', text: streamError, key: 'error' })
        } else {
          handlers.onProgress?.(event as ProgressEvent)
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }

  if (!sawAnyFrame) {
    // 一帧都没收到：更可能是通道问题而不是业务问题，允许回退
    throw new ChatStreamUnavailableError('未收到任何流式数据')
  }
  if (streamError) throw new Error(streamError)
  if (!result) throw new Error('连接中断，未收到完整回复')

  return result
}

/** 从非 2xx 响应里取出可读错误 */
async function readErrorDetail(response: Response): Promise<string> {
  try {
    const data = await response.json()
    return data?.detail || `请求失败（HTTP ${response.status}）`
  } catch {
    return `请求失败（HTTP ${response.status}）`
  }
}

export const agentApi = {
  /**
   * 发送消息给 Agent（不传 conversation_id 则开新会话）
   */
  chat: (data: AgentMessageRequest) => {
    return request.post<AgentMessageResponse>('/api/v1/agent/chat', data)
  },

  /**
   * 获取会话列表（按最近使用倒序）
   */
  listConversations: (params?: { limit?: number; offset?: number }) => {
    return request.get<{ conversations: ConversationSummary[]; total: number }>(
      '/api/v1/agent/conversations',
      { params },
    )
  },

  /**
   * 获取某个会话及其全部消息
   */
  getConversation: (conversationId: string, params?: { limit?: number; offset?: number }) => {
    return request.get<ConversationDetail>(
      `/api/v1/agent/conversations/${conversationId}`,
      { params },
    )
  },

  /**
   * 删除会话（连同其中的消息）
   */
  deleteConversation: (conversationId: string) => {
    return request.delete(`/api/v1/agent/conversations/${conversationId}`)
  },
}

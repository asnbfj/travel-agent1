<template>
  <div class="ai-chat-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1>🧳 智能旅行规划</h1>
      <p class="subtitle">告诉我你的旅行想法，AI 帮你规划完美行程</p>
    </div>

    <!-- 快速模板 -->
    <div class="quick-templates" v-if="messages.length === 0">
      <h3>🚀 试试这些</h3>
      <div class="template-list">
        <a-card
          v-for="template in templates"
          :key="template.title"
          :hoverable="true"
          class="template-card"
          @click="useTemplate(template)"
        >
          <template #cover>
            <div class="template-icon">{{ template.icon }}</div>
          </template>
          <div class="template-content">
            <div class="template-title">{{ template.title }}</div>
            <div class="template-desc">{{ template.desc }}</div>
          </div>
        </a-card>
      </div>
    </div>

    <!-- 聊天消息区域 -->
    <div class="chat-container" ref="chatContainer">
      <div class="message-list">
        <div
          v-for="msg in messages"
          :key="msg.id"
          :class="['message', msg.role]"
        >
          <div class="message-avatar">
            <a-avatar v-if="msg.role === 'user'" :size="36">
              <icon-user />
            </a-avatar>
            <a-avatar v-else :size="36" class="bot-avatar">
              <icon-robot />
            </a-avatar>
          </div>

          <div class="message-content">
            <div class="message-header">
              <span class="sender-name">{{ msg.role === 'user' ? '你' : 'TravelAI' }}</span>
              <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
            </div>

            <div class="message-body">
              <!-- 用户消息 -->
              <div v-if="msg.role === 'user'" class="user-message">
                {{ msg.content }}
              </div>

              <!-- AI 消息 -->
              <div v-else class="ai-message">
                <!-- 天气信息 -->
                <div v-if="msg.weather_info" class="weather-card">
                  <div class="weather-header">
                    <icon-environment />
                    <span>{{ msg.weather_info.city }} 天气预报</span>
                  </div>
                  <div class="weather-days">
                    <div
                      v-for="day in msg.weather_info.forecasts.slice(0, 5)"
                      :key="day.date"
                      class="weather-day"
                    >
                      <div class="day-name">{{ day.weekday }}</div>
                      <div class="day-icon">{{ day.icon }}</div>
                      <div class="day-weather">{{ day.weather }}</div>
                      <div class="day-temp">{{ formatTemp(day.temp_low) }}° ~ {{ formatTemp(day.temp_high) }}°</div>
                    </div>
                  </div>
                  <div class="weather-tips" v-if="msg.weather_info.tips">
                    💡 {{ msg.weather_info.tips }}
                  </div>
                  <div class="weather-source">
                    数据来源：{{ msg.weather_info.source || '高德地图' }}
                    <template v-if="msg.weather_info.report_time">
                      · 发布 {{ msg.weather_info.report_time }}
                    </template>
                  </div>
                </div>

                <!-- 本次调用的线上工具 -->
                <div v-if="msg.tool_calls?.length" class="tool-calls">
                  <span class="tool-label">已调用线上接口：</span>
                  <a-tag
                    v-for="(call, i) in uniqueToolCalls(msg.tool_calls)"
                    :key="i"
                    class="tool-tag"
                    size="small"
                  >
                    {{ toolLabel(call.name) }}
                  </a-tag>
                </div>

                <!-- 纯文本回复 -->
                <div class="markdown-content" v-html="renderMarkdown(msg.content)"></div>

                <!-- 行程操作：仅在看起来是完整行程的回复上出现 -->
                <div v-if="isItinerary(msg.content)" class="export-bar">
                  <a-button
                    type="primary"
                    size="small"
                    :loading="exportingId === msg.id"
                    @click="handleExportPdf(msg)"
                  >
                    <template #icon><icon-download /></template>
                    生成 PDF 行程
                  </a-button>

                  <a-button
                    v-if="!savedTrips[msg.id]"
                    size="small"
                    @click="openSaveModal(msg)"
                  >
                    <template #icon><icon-save /></template>
                    保存到我的行程
                  </a-button>
                  <a-button
                    v-else
                    size="small"
                    status="success"
                    @click="goToTrip(savedTrips[msg.id])"
                  >
                    <template #icon><icon-check /></template>
                    已保存 · 查看行程
                  </a-button>

                  <span class="export-hint">下载后文字可选中、可搜索</span>
                </div>
              </div>
            </div>

            <!-- 建议操作 -->
            <div
              v-if="msg.suggested_actions?.length && msg.role === 'assistant'"
              class="suggested-actions"
            >
              <span class="action-label">你可以：</span>
              <a-tag
                v-for="action in msg.suggested_actions"
                :key="action"
                class="action-tag"
                @click="handleAction(action)"
              >
                {{ action }}
              </a-tag>
            </div>
          </div>
        </div>

        <!-- 加载状态 -->
        <div v-if="loading" class="message assistant loading">
          <div class="message-avatar">
            <a-avatar :size="36" class="bot-avatar">
              <icon-robot />
            </a-avatar>
          </div>
          <div class="message-content">
            <a-typography-paragraph class="typing-indicator">
              <a-spin :size="16" /> TravelAI 正在规划中...
            </a-typography-paragraph>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <a-textarea
        v-model="inputMessage"
        placeholder="描述你的旅行计划... 例如：我想去日本东京，4月份，5天3人，预算2万"
        :auto-size="{ minRows: 2, maxRows: 5 }"
        @press-enter="handleSend"
      />
      <div class="input-actions">
        <a-button @click="clearHistory">
          <template #icon><icon-delete /></template>
          清空记录
        </a-button>
        <a-button type="primary" @click="handleSend" :disabled="!inputMessage.trim()">
          <template #icon><icon-send /></template>
          发送
        </a-button>
      </div>
    </div>

    <!-- 保存到「我的行程」：字段由服务端推断预填，用户确认后落库 -->
    <a-modal
      v-model:visible="saveModalVisible"
      title="保存到我的行程"
      :ok-loading="savingTrip"
      :mask-closable="false"
      unmount-on-close
      @before-ok="confirmSaveTrip"
    >
      <a-spin :loading="prefillLoading" style="width: 100%">
        <a-form :model="saveForm" layout="vertical">
          <a-form-item field="title" label="行程标题" :rules="[{ required: true, message: '请输入标题' }]">
            <a-input v-model="saveForm.title" placeholder="例如：北海 3 天行程" />
          </a-form-item>

          <a-form-item field="destination" label="目的地" :rules="[{ required: true, message: '请输入目的地' }]">
            <a-input
              v-model="saveForm.destination"
              placeholder="例如：北海"
              :status="prefillFailedDestination ? 'warning' : undefined"
            />
          </a-form-item>

          <a-form-item field="dates" label="出行日期" :rules="[{ required: true, message: '请选择日期' }]">
            <a-range-picker v-model="saveDateRange" style="width: 100%" />
          </a-form-item>

          <a-grid :cols="24" :col-gap="16">
            <a-grid-item :span="12">
              <a-form-item field="travelers" label="出行人数">
                <a-input-number v-model="saveForm.travelers" :min="1" :max="50" style="width: 100%" />
              </a-form-item>
            </a-grid-item>
            <a-grid-item :span="12">
              <a-form-item field="budget" label="预算（元）">
                <a-input-number v-model="saveForm.budget" :min="0" :step="1000" style="width: 100%" />
              </a-form-item>
            </a-grid-item>
          </a-grid>

          <a-alert v-if="prefillNote" type="info" :show-icon="true">
            {{ prefillNote }}
          </a-alert>
        </a-form>
      </a-spin>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import {
  agentApi,
  exportItineraryPdf,
  readExportError,
  type ChatMessage,
} from '../api/agent'
import { tripApi } from '../api/trips'
import { useTripStore } from '../stores/trip'

const router = useRouter()
const tripStore = useTripStore()
const inputMessage = ref('')
const messages = ref<Array<ChatMessage & { weather_info?: any; itinerary?: any; suggested_actions?: string[]; tool_calls?: Array<{ name: string; args: Record<string, any> }> }>>([])
const loading = ref(false)
const chatContainer = ref<HTMLElement>()
/** 正在导出 PDF 的消息 id（用于按钮 loading 态） */
const exportingId = ref<string | null>(null)

/** 与后端约定一致：足够长且像行程的回复才提供导出/保存入口 */
const isItinerary = (content?: string) => (content?.trim().length ?? 0) >= 400

// ---------------------------------------------------------------- 保存到我的行程

/** 已保存的消息 id -> 行程 id（保存后按钮变为「查看行程」） */
const savedTrips = ref<Record<string, string>>({})
const saveModalVisible = ref(false)
const prefillLoading = ref(false)
const savingTrip = ref(false)
/** 服务端推断不出目的地时的提示 */
const prefillNote = ref('')
const prefillFailedDestination = ref(false)
const saveForm = reactive({ title: '', destination: '', travelers: 1, budget: 0 })
const saveDateRange = ref<string[]>([])
/** 本次要保存的规划来源 */
const planSource = ref<{
  msgId: string
  content: string
  weather_info: Record<string, any> | null
  tool_calls: Array<{ name: string; args: Record<string, any> }>
  user_message?: string
}>({ msgId: '', content: '', weather_info: null, tool_calls: [] })

/** 找到某条 AI 回复之前最近的用户提问（用于推断天数/人数/预算/日期） */
const findUserMessage = (assistantMsgId: string) => {
  const index = messages.value.findIndex((m) => m.id === assistantMsgId)
  if (index < 0) return undefined
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages.value[i].role === 'user') return messages.value[i].content
  }
  return undefined
}

const goToTrip = (tripId: string) => router.push(`/trip/${tripId}`)

/** 打开保存弹窗，并用服务端推断结果预填 */
const openSaveModal = async (msg: {
  id: string
  content: string
  weather_info?: any
  tool_calls?: Array<{ name: string; args: Record<string, any> }>
}) => {
  planSource.value = {
    msgId: msg.id,
    content: msg.content,
    weather_info: msg.weather_info ?? null,
    tool_calls: msg.tool_calls ?? [],
    user_message: findUserMessage(msg.id),
  }
  saveForm.title = ''
  saveForm.destination = ''
  saveForm.travelers = 1
  saveForm.budget = 0
  saveDateRange.value = []
  prefillNote.value = ''
  prefillFailedDestination.value = false
  saveModalVisible.value = true
  prefillLoading.value = true

  try {
    const inferred = await tripApi.extractPlan({
      content: planSource.value.content,
      weather_info: planSource.value.weather_info,
      tool_calls: planSource.value.tool_calls,
      user_message: planSource.value.user_message,
    })
    saveForm.title = inferred.title
    saveForm.destination = inferred.destination
    saveForm.travelers = inferred.travelers
    saveForm.budget = inferred.budget
    saveDateRange.value = [inferred.start_date, inferred.end_date]

    // 目的地推断不出来时不要静默留空，明确提示用户补填
    if (!inferred.destination) {
      prefillFailedDestination.value = true
      prefillNote.value = '未能从对话中识别目的地，请手动填写后再保存。'
    } else {
      prefillNote.value = `已按对话自动填充（共 ${inferred.days_count} 天），请确认日期与人数是否正确。`
    }
  } catch {
    prefillNote.value = '自动填充失败，请手动填写行程信息。'
  } finally {
    prefillLoading.value = false
  }
}

/** 确认保存（由弹窗的 before-ok 触发；返回 false 可阻止关闭） */
const confirmSaveTrip = async () => {
  if (!saveForm.title.trim()) {
    Message.warning('请填写行程标题')
    return false
  }
  if (!saveForm.destination.trim()) {
    Message.warning('请填写目的地')
    return false
  }
  if (saveDateRange.value?.length !== 2) {
    Message.warning('请选择出行日期')
    return false
  }
  if (saveDateRange.value[0] > saveDateRange.value[1]) {
    Message.warning('返回日期不能早于出发日期')
    return false
  }

  savingTrip.value = true
  try {
    const trip = await tripStore.createFromPlan({
      title: saveForm.title.trim(),
      destination: saveForm.destination.trim(),
      start_date: saveDateRange.value[0],
      end_date: saveDateRange.value[1],
      budget: saveForm.budget,
      travelers: saveForm.travelers,
      requirements: { source: 'ai_chat' },
      content: planSource.value.content,
      weather_info: planSource.value.weather_info,
      source_message: planSource.value.user_message,
    })
    savedTrips.value = { ...savedTrips.value, [planSource.value.msgId]: trip.id }
    Message.success('已保存到「我的行程」')
    return true
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '保存失败，请重试')
    return false
  } finally {
    savingTrip.value = false
  }
}

/** 线上工具名称 -> 展示名 */
const TOOL_LABELS: Record<string, string> = {
  get_weather: '高德地图 · 天气查询',
  search_attractions: '博查 · 联网景点搜索',
  search_hotels: '博查 · 联网酒店搜索',
  plan_route: '高德地图 · 路线规划',
}

const toolLabel = (name: string) => TOOL_LABELS[name] || name

/** 同一工具多轮调用时去重展示 */
const uniqueToolCalls = (calls: Array<{ name: string }>) => {
  const seen = new Set<string>()
  return calls.filter((c) => {
    if (seen.has(c.name)) return false
    seen.add(c.name)
    return true
  })
}

/** 温度可能为 null（上游未提供），避免渲染成 "null°" */
const formatTemp = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : value

// 快速模板
const templates = [
  { icon: '🌸', title: '日本赏樱', desc: '4月初去日本东京，5天，2人，赏樱之旅' },
  { icon: '🏖', title: '海岛度假', desc: '想去三亚，3天，亲子游，预算1万' },
  { icon: '🏔', title: '云南自由行', desc: '丽江大理，7天，2人，休闲游' },
  { icon: '🇹🇭', title: '泰国泼水节', desc: '4月中旬去曼谷，4天，预算5000' },
]

const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const renderMarkdown = (content: string) => {
  // 简单的 Markdown 渲染
  return content
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/\n/g, '<br>')
}

const useTemplate = (template: typeof templates[0]) => {
  inputMessage.value = template.desc
  handleSend()
}

/** 触发浏览器下载 */
const triggerDownload = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // 交还内存：下载已开始，无需再持有 blob URL
  URL.revokeObjectURL(url)
}

/** 生成 PDF 并下载 */
const handleExportPdf = async (msg: { id: string; content: string; weather_info?: any }) => {
  if (exportingId.value) return // 防止连点导致并发导出
  exportingId.value = msg.id
  try {
    const city = msg.weather_info?.city
    const { blob, filename } = await exportItineraryPdf({
      content: msg.content,
      // 有目的地时给一个像样的文档标题，否则交由后端从正文提取
      title: city ? `${city} 旅行行程规划` : undefined,
      destination: city,
      weather_info: msg.weather_info,
    })
    triggerDownload(blob, filename)
    Message.success('PDF 已开始下载')
  } catch (error) {
    Message.error(await readExportError(error))
  } finally {
    exportingId.value = null
  }
}

const handleSend = async () => {
  const content = inputMessage.value.trim()
  if (!content || loading.value) return

  // 添加用户消息
  messages.value.push({
    id: Date.now().toString(),
    role: 'user',
    content,
    timestamp: new Date().toISOString(),
  })

  inputMessage.value = ''
  loading.value = true
  scrollToBottom()

  try {
    const response = await agentApi.chat({ message: content })

    // 添加 AI 回复
    messages.value.push({
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: response.message,
      timestamp: new Date().toISOString(),
      weather_info: response.weather_info,
      suggested_actions: response.suggested_actions,
      tool_calls: response.tool_calls,
    })
  } catch (error) {
    Message.error('发送失败，请重试')
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

const handleAction = (action: string) => {
  if (action.includes('修改') || action.includes('调整') || action.includes('换')) {
    inputMessage.value = '帮我调整一下行程，我想...'
  } else if (action.includes('导出')) {
    // 导出最近一条「完整行程」回复
    const target = [...messages.value]
      .reverse()
      .find((m) => m.role === 'assistant' && isItinerary(m.content))
    if (target) {
      handleExportPdf(target)
    } else {
      Message.warning('还没有可导出的完整行程，先让我帮你规划一份吧')
    }
  }
}

const clearHistory = async () => {
  try {
    await agentApi.clearHistory()
    messages.value = []
    Message.success('已清空对话记录')
  } catch (error) {
    Message.error('清空失败')
  }
}

const scrollToBottom = () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

onMounted(() => {
  // 加载历史记录
  agentApi.getHistory().then(res => {
    messages.value = res.messages
    scrollToBottom()
  }).catch(() => {
    // 未登录或加载失败时忽略
  })
})
</script>

<style scoped>
.ai-chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 140px);
  max-width: 900px;
  margin: 0 auto;
  padding: 0 16px;
}

.page-header {
  text-align: center;
  padding: 24px 0;
}

.page-header h1 {
  font-size: 28px;
  margin-bottom: 8px;
}

.subtitle {
  color: #86909c;
  font-size: 14px;
}

.quick-templates {
  margin-bottom: 24px;
}

.quick-templates h3 {
  font-size: 16px;
  margin-bottom: 12px;
  color: #86909c;
}

.template-list {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.template-card {
  cursor: pointer;
  transition: transform 0.2s;
}

.template-card:hover {
  transform: translateY(-4px);
}

.template-icon {
  font-size: 48px;
  text-align: center;
  padding: 24px 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.template-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.template-desc {
  font-size: 12px;
  color: #86909c;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.message.user {
  flex-direction: row-reverse;
}

.message-content {
  max-width: 75%;
}

.message.user .message-content {
  align-items: flex-end;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
}

.message.user .message-header {
  flex-direction: row-reverse;
}

.sender-name {
  font-weight: 600;
}

.message-time {
  color: #86909c;
}

.user-message {
  background: #165dff;
  color: white;
  padding: 12px 16px;
  border-radius: 16px 16px 4px 16px;
}

.ai-message {
  background: #f2f3f5;
  padding: 16px;
  border-radius: 16px 16px 16px 4px;
  width: 100%;
}

.weather-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 16px;
  border-radius: 12px;
  margin-bottom: 16px;
}

.weather-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
}

.weather-days {
  display: flex;
  gap: 8px;
}

.weather-day {
  text-align: center;
  flex: 1;
}

.day-icon {
  font-size: 24px;
  margin: 4px 0;
}

.day-weather {
  font-size: 12px;
  opacity: 0.9;
}

.day-temp {
  font-size: 11px;
  opacity: 0.8;
}

.weather-tips {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.2);
  font-size: 13px;
}

.itinerary-preview {
  background: white;
  padding: 16px;
  border-radius: 12px;
  margin-bottom: 16px;
}

.itinerary-header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #165dff;
  font-weight: 600;
  margin-bottom: 12px;
}

.itinerary-actions {
  display: flex;
  gap: 8px;
}

.suggested-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.action-label {
  font-size: 12px;
  color: #86909c;
}

.action-tag {
  cursor: pointer;
}

.input-area {
  padding: 16px 0;
  border-top: 1px solid #e5e6eb;
  background: white;
}

.input-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
}

.loading .ai-message {
  display: flex;
  align-items: center;
  gap: 8px;
}

.typing-indicator {
  margin: 0;
  color: #86909c;
}

/* 已调用的线上工具 */
.tool-calls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.tool-label {
  font-size: 12px;
  color: #86909c;
}

.tool-tag {
  background: #e8f3ff;
  color: #165dff;
  border: none;
}

/* 行程导出 */
.export-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #e5e6eb;
  flex-wrap: wrap;
}

.export-hint {
  font-size: 12px;
  color: #86909c;
}

.weather-source {
  margin-top: 8px;
  font-size: 11px;
  opacity: 0.75;
}
</style>

<template>
  <div class="chat-page" :class="{ 'chat-page--empty': messages.length === 0 && !loading }">
    <header class="chat-head">
      <h1 class="title-song">智能规划</h1>
      <p class="chat-lede">
        把想去的地方、日期、人数和预算说清楚。它会联网查完天气、景点、住宿和路线，
        再排成一份每天的时刻表；哪里不合适，直接说要改什么。
      </p>
    </header>

    <!-- 空状态：直接给几句能用的开头 -->
    <section v-if="messages.length === 0 && !loading" class="samples">
      <div class="samples-head">
        <span>可以这样开头</span>
        <span class="muted">点一条直接发出去</span>
      </div>
      <button
        v-for="template in templates"
        :key="template.title"
        type="button"
        class="sample"
        @click="useTemplate(template)"
      >
        <span class="sample-text title-song">{{ template.desc }}</span>
        <span class="sample-tag">{{ template.title }}</span>
      </button>
    </section>

    <!-- 对话记录：一条竖线串起每一轮 -->
    <div ref="chatContainer" class="chat-log">
      <ol class="log" aria-live="polite">
        <li
          v-for="msg in messages"
          :key="msg.id"
          :class="['entry', `entry--${msg.role}`]"
        >
          <div class="entry-gutter">
            <span class="entry-mark"></span>
          </div>

          <div class="entry-body">
            <div class="entry-head">
              <span class="entry-who">{{ msg.role === 'user' ? '你' : 'TravelAI' }}</span>
              <span class="entry-time num">{{ formatTime(msg.timestamp) }}</span>
            </div>

            <!-- 用户：原话放在浅底上 -->
            <div v-if="msg.role === 'user'" class="said">
              {{ msg.content }}
            </div>

            <!-- AI：这一轮的记录 -->
            <div v-else class="reply">
              <div v-if="msg.tool_calls?.length" class="calls">
                <span class="calls-label">本轮调用</span>
                <span
                  v-for="(call, i) in uniqueToolCalls(msg.tool_calls)"
                  :key="i"
                  class="call-chip"
                >
                  {{ toolLabel(call.name) }}
                </span>
              </div>

              <WeatherCard v-if="msg.weather_info" :weather="msg.weather_info" class="forecast-slot" />

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
                  已保存，打开行程
                </a-button>

                <span class="export-hint">PDF 里的文字可选中、可搜索</span>
              </div>

              <div
                v-if="msg.suggested_actions?.length"
                class="suggested-actions"
              >
                <span class="action-label">接下来可以</span>
                <button
                  v-for="action in msg.suggested_actions"
                  :key="action"
                  type="button"
                  class="action-chip"
                  @click="handleAction(action)"
                >
                  {{ action }}
                </button>
              </div>
            </div>
          </div>
        </li>

        <li v-if="loading" class="entry entry--assistant">
          <div class="entry-gutter">
            <span class="entry-mark entry-mark--busy"></span>
          </div>
          <div class="entry-body">
            <div class="entry-head"><span class="entry-who">TravelAI</span></div>
            <div class="busy">
              <span class="busy-ruler" aria-hidden="true"><span class="busy-marker"></span></span>
              <span class="busy-text">正在规划。需要联网查几次资料，可能要十几秒。</span>
            </div>
          </div>
        </li>
      </ol>
    </div>

    <!-- 输入 -->
    <div class="composer">
      <a-textarea
        v-model="inputMessage"
        placeholder="例如：4 月初去日本东京赏樱，5 天 2 人，预算 2 万，想看夜樱也想留半天给镰仓"
        :auto-size="{ minRows: 2, maxRows: 5 }"
        @press-enter="handleSend"
      />
      <div class="composer-actions">
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
import WeatherCard from '../components/common/WeatherCard.vue'
import { renderMarkdown } from '../utils/markdown'

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
      prefillNote.value = '没能从对话里认出目的地，请手动填写后再保存。'
    } else {
      prefillNote.value = `已按对话自动填写（共 ${inferred.days_count} 天），请确认日期与人数。`
    }
  } catch {
    prefillNote.value = '自动填写失败，请手动填好行程信息。'
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

/** 线上工具名称 -> 展示名（说清数据从哪来） */
const TOOL_LABELS: Record<string, string> = {
  get_weather: '天气查询（高德地图）',
  search_attractions: '联网景点搜索（博查）',
  search_hotels: '联网酒店搜索（博查）',
  plan_route: '路线规划（高德地图）',
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

// 快速模板：每句都是能直接用的真实需求
const templates = [
  { title: '赏樱', desc: '4 月初去日本东京赏樱，5 天，2 人，预算 2 万' },
  { title: '亲子海岛', desc: '想去三亚，3 天，带孩子，预算 1 万，别安排太赶' },
  { title: '云南自由行', desc: '丽江大理，7 天，2 人，休闲游，住得舒服一点' },
  { title: '泰国泼水节', desc: '4 月中旬去曼谷，4 天，预算 5000' },
]

const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
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
      Message.warning('还没有可导出的完整行程，先让我帮你排一份')
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
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 156px);
  min-height: 520px;
  padding-top: 26px;
}

/* 还没有对话时不要撑满一屏，否则示例和输入框之间会出现大片空白 */
.chat-page--empty {
  height: auto;
  min-height: 0;
}

.chat-page--empty .chat-log {
  flex: none;
  overflow: visible;
  padding-bottom: 0;
}

.chat-head {
  flex: none;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--rule-strong);
}

.chat-head h1 {
  font-size: 26px;
}

.chat-lede {
  margin: 8px 0 0;
  max-width: 70ch;
  color: var(--ink-2);
  font-size: 14px;
}

/* ————————————————————————— 示例开头 ————————————————————————— */

.samples {
  flex: none;
  margin-top: 22px;
  border: 1px solid var(--rule);
  background: var(--plot);
}

.samples-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 14px;
  border-bottom: 1px solid var(--rule);
  font-size: 12px;
  color: var(--ink-3);
  background: var(--plot-2);
}

.sample {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 18px;
  width: 100%;
  padding: 13px 14px;
  border: none;
  border-top: 1px solid var(--rule);
  background: transparent;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: var(--ink);
  transition: background 0.15s ease;
}

.sample:first-of-type {
  border-top: none;
}

.sample:hover {
  background: var(--magenta-tint);
}

.sample-text {
  font-size: 16px;
}

.sample-tag {
  flex: none;
  font-size: 12px;
  color: var(--ink-3);
}

/* ————————————————————————— 对话记录 ————————————————————————— */

.chat-log {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 22px 4px 8px 0;
}

.log {
  list-style: none;
  margin: 0;
  padding: 0 0 0 12px;
  position: relative;
}

/* 贯穿整段对话的竖线：一轮就是线上的一个站点 */
.log::before {
  content: '';
  position: absolute;
  left: 3px;
  top: 8px;
  bottom: 8px;
  width: 1px;
  background: var(--rule);
}

.entry {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 16px;
  padding-bottom: 26px;
  position: relative;
}

.entry-gutter {
  display: flex;
  justify-content: center;
  padding-top: 5px;
}

.entry-mark {
  width: 7px;
  height: 7px;
  background: var(--plot);
  border: 1px solid var(--ink-2);
  position: relative;
  z-index: 1;
}

.entry--user .entry-mark {
  background: var(--ink);
  border-color: var(--ink);
}

.entry--assistant .entry-mark {
  border-color: var(--magenta);
  border-width: 2px;
}

.entry-mark--busy {
  background: var(--magenta);
  border-color: var(--magenta);
  animation: busy-pulse 1.2s ease-in-out infinite;
}

@keyframes busy-pulse {
  50% {
    opacity: 0.25;
  }
}

.entry-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 7px;
}

.entry-who {
  font-size: 13px;
  font-weight: 600;
}

.entry-time {
  font-size: 11px;
  color: var(--ink-3);
}

/* 用户原话：浅底 + 左侧墨线，不做气泡 */
.said {
  display: inline-block;
  max-width: 66ch;
  padding: 11px 15px;
  background: var(--plot-2);
  border-left: 2px solid var(--ink);
  font-size: 15px;
  white-space: pre-wrap;
}

/* AI 回复：一块绘图区 */
.reply {
  border: 1px solid var(--rule);
  background: var(--plot);
  padding: 16px 18px;
}

.calls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--rule);
}

.calls-label {
  font-size: 12px;
  color: var(--ink-3);
}

.call-chip {
  font-size: 12px;
  color: var(--ink-2);
  border: 1px solid var(--rule-strong);
  padding: 1px 8px;
}

/* 天气面板由 WeatherCard 统一渲染，这里只留外边距 */
.forecast-slot {
  margin-bottom: 18px;
}

/* ————————————————————————— 行程导出 ————————————————————————— */

.export-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 20px;
  padding-top: 14px;
  border-top: 1px solid var(--rule);
}

.export-hint {
  font-size: 12px;
  color: var(--ink-3);
}

.suggested-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.action-label {
  font-size: 12px;
  color: var(--ink-3);
}

.action-chip {
  font: inherit;
  font-size: 13px;
  color: var(--ink-2);
  background: transparent;
  border: 1px solid var(--rule-strong);
  padding: 2px 10px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.action-chip:hover {
  color: var(--magenta);
  border-color: var(--magenta);
}

/* ————————————————————————— 进行中 ————————————————————————— */

.busy {
  display: flex;
  align-items: center;
  gap: 14px;
  border: 1px solid var(--rule);
  background: var(--plot);
  padding: 14px 16px;
}

.busy-ruler {
  position: relative;
  flex: none;
  width: 44px;
  height: 9px;
  background-image: repeating-linear-gradient(
    to right,
    var(--rule-strong) 0 1px,
    transparent 1px 11px
  );
}

.busy-marker {
  position: absolute;
  top: 0;
  left: 0;
  width: 2px;
  height: 9px;
  background: var(--magenta);
  animation: sweep 1.6s ease-in-out infinite alternate;
}

@keyframes sweep {
  from {
    left: 0;
  }
  to {
    left: 42px;
  }
}

.busy-text {
  font-size: 13px;
  color: var(--ink-2);
}

/* ————————————————————————— 输入 ————————————————————————— */

.composer {
  flex: none;
  border: 1px solid var(--rule);
  background: var(--plot);
  padding: 12px;
}

.composer :deep(.arco-textarea-wrapper) {
  border: none;
  background: transparent;
  padding: 0;
}

.composer :deep(.arco-textarea) {
  background: transparent;
  font-size: 15px;
  padding: 2px 4px;
}

.composer-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--rule);
}

@media (max-width: 860px) {
  .chat-page {
    height: auto;
    min-height: 0;
  }

  .chat-log {
    overflow: visible;
    padding-right: 0;
  }

  .entry {
    gap: 12px;
  }
}
</style>

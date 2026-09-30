<template>
  <div class="chat-page" :class="{ 'chat-page--empty': messages.length === 0 && !loading }">
    <!-- 会话栏：宽屏常驻且可收缩；窄屏改走抽屉（见文件末尾） -->
    <ConversationSidebar
      v-if="!isNarrow"
      class="chat-side"
      :conversations="conversationStore.conversations"
      :active-id="conversationStore.activeId"
      :collapsed="sidebarCollapsed"
      :loading="conversationStore.loadingList"
      @create="handleNewConversation"
      @select="handleSelectConversation"
      @remove="handleDeleteConversation"
      @toggle-collapse="toggleSidebar"
    />

    <header class="chat-head">
      <div v-if="isNarrow" class="chat-head-bar">
        <button type="button" class="rail-btn" @click="drawerOpen = true">
          <icon-menu />
          <span>会话</span>
        </button>
        <button type="button" class="rail-btn" @click="handleNewConversation">
          <icon-plus />
          <span>新对话</span>
        </button>
      </div>
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
                <button
                  v-if="stepsOf(msg.id).length"
                  type="button"
                  class="calls-toggle"
                  :aria-expanded="expandedSteps[msg.id] ? 'true' : 'false'"
                  @click="toggleSteps(msg.id)"
                >
                  <icon-down v-if="!expandedSteps[msg.id]" />
                  <icon-up v-else />
                  执行过程
                  <span class="calls-toggle-num num">{{ stepsOf(msg.id).length }}</span>
                </button>
              </div>

              <!-- 执行过程：本地刚跑完的那一轮才有（历史消息不存这些过程细节） -->
              <ProgressTimeline
                v-if="stepsOf(msg.id).length && expandedSteps[msg.id]"
                class="steps-in-message"
                :steps="stepsOf(msg.id)"
                :now="now"
              />

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
            <ProgressTimeline :steps="liveSteps" :now="now" />
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

  <!-- 窄屏抽屉：盖在聊天区之上，点遮罩或「关闭」收起 -->
  <div v-if="isNarrow && drawerOpen" class="drawer-layer">
    <div class="drawer-mask" @click="drawerOpen = false" />
    <ConversationSidebar
      variant="drawer"
      :conversations="conversationStore.conversations"
      :active-id="conversationStore.activeId"
      :loading="conversationStore.loadingList"
      @create="handleNewConversation"
      @select="handleSelectConversation"
      @remove="handleDeleteConversation"
      @close="drawerOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import {
  exportItineraryPdf,
  readExportError,
  sendChatMessage,
  type ChatMessage,
} from '../api/agent'
import { tripApi } from '../api/trips'
import { useTripStore } from '../stores/trip'
import { useConversationStore } from '../stores/conversation'
import ConversationSidebar from '../components/chat/ConversationSidebar.vue'
import ProgressTimeline from '../components/chat/ProgressTimeline.vue'
import WeatherCard from '../components/common/WeatherCard.vue'
import { renderMarkdown } from '../utils/markdown'
import { reduceProgress, type ProgressStep } from '../utils/progress'
import { formatClock } from '../utils/time'

const router = useRouter()
const tripStore = useTripStore()
const conversationStore = useConversationStore()
const inputMessage = ref('')
const loading = ref(false)
const chatContainer = ref<HTMLElement>()

/** 消息列表由会话 store 持有：切换会话时整体替换，不再散落在视图里 */
const messages = computed(() => conversationStore.messages)

// ---------------------------------------------------------------- 会话栏

const SIDEBAR_COLLAPSED_KEY = 'travelai:chat-sidebar-collapsed'
/** 宽屏会话栏是否收起（记住用户的选择） */
const sidebarCollapsed = ref(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1')
/** 窄屏抽屉开关 */
const drawerOpen = ref(false)
const isNarrow = ref(false)
let narrowQuery: MediaQueryList | null = null

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed.value ? '1' : '0')
}

const onBreakpointChange = (event: MediaQueryListEvent) => {
  isNarrow.value = event.matches
  // 切回宽屏后抽屉不再有意义，避免它悬在页面上
  if (!event.matches) drawerOpen.value = false
}
/** 正在导出 PDF 的消息 id（用于按钮 loading 态） */
const exportingId = ref<string | null>(null)

// ---------------------------------------------------------------- 执行过程

/** 本次请求的实时步骤（跑完即清空，所以放在视图而不是会话 store 里） */
const liveSteps = ref<ProgressStep[]>([])
/** 已跑完的步骤按消息 id 留着，便于回看「刚才调用了什么、有没有重试」 */
const stepsByMessage = ref<Record<string, ProgressStep[]>>({})
/** 哪几条消息的执行过程被展开了 */
const expandedSteps = ref<Record<string, boolean>>({})

/** 用于给进行中的步骤算实时耗时；只在请求期间跑，避免空转 */
const now = ref(Date.now())
let ticker: number | null = null

const startTicker = () => {
  stopTicker()
  now.value = Date.now()
  ticker = window.setInterval(() => {
    now.value = Date.now()
  }, 200)
}

const stopTicker = () => {
  if (ticker !== null) {
    window.clearInterval(ticker)
    ticker = null
  }
}

const stepsOf = (messageId: string): ProgressStep[] => stepsByMessage.value[messageId] ?? []

const toggleSteps = (messageId: string) => {
  expandedSteps.value[messageId] = !expandedSteps.value[messageId]
}

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

const formatTime = (timestamp: string) => formatClock(timestamp)


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
  conversationStore.appendMessage({
    id: `local-user-${Date.now()}`,
    role: 'user',
    content,
    timestamp: new Date().toISOString(),
  })

  inputMessage.value = ''
  loading.value = true
  liveSteps.value = []
  startTicker()
  scrollToBottom()

  try {
    const response = await sendChatMessage(
      {
        message: content,
        // 不传则服务端开新会话；传了则续在当前会话里
        conversation_id: conversationStore.activeId,
      },
      {
        // 边跑边显示「执行到哪一步」
        onProgress: (event) => {
          reduceProgress(liveSteps.value, event)
          scrollToBottom()
        },
      },
    )

    if (response.conversation_id) {
      conversationStore.bindActiveConversation(response.conversation_id)
    }

    const assistantId = `local-assistant-${Date.now()}`

    // 添加 AI 回复
    conversationStore.appendMessage({
      id: assistantId,
      role: 'assistant',
      content: response.message,
      timestamp: new Date().toISOString(),
      weather_info: response.weather_info,
      suggested_actions: response.suggested_actions,
      tool_calls: response.tool_calls,
    })

    // 这一轮的执行过程留在回复下面，可展开回看
    if (liveSteps.value.length) {
      const finished = liveSteps.value.map((step) =>
        step.status === 'running'
          ? { ...step, status: 'done' as const, durationMs: Date.now() - step.startedAt }
          : step,
      )
      stepsByMessage.value[assistantId] = finished
    }

    // 首条提问的标题由服务端生成，刷新列表好把它显示出来
    conversationStore.fetchConversations().catch(() => {})
  } catch (error) {
    Message.error(error instanceof Error ? error.message : '发送失败，请重试')
  } finally {
    loading.value = false
    liveSteps.value = []
    stopTicker()
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

// ---------------------------------------------------------------- 会话操作

/** 新建一段会话：只清空本地状态，首条消息发出后服务端才真正落库 */
const handleNewConversation = () => {
  conversationStore.startNewConversation()
  savedTrips.value = {}
  // 执行过程是按本地消息 id 记的，换会话后这些 id 都不再存在
  stepsByMessage.value = {}
  expandedSteps.value = {}
  inputMessage.value = ''
  drawerOpen.value = false
}

/** 切换会话 */
const handleSelectConversation = async (conversationId: string) => {
  drawerOpen.value = false
  if (conversationId === conversationStore.activeId) return
  try {
    await conversationStore.selectConversation(conversationId)
    // 「已保存到我的行程」与执行过程都是按本地消息 id 记的，换了会话不能沿用
    savedTrips.value = {}
    stepsByMessage.value = {}
    expandedSteps.value = {}
    scrollToBottom()
  } catch (error) {
    Message.error('加载会话失败，请重试')
  }
}

/** 删除会话 */
const handleDeleteConversation = async (conversationId: string) => {
  try {
    await conversationStore.removeConversation(conversationId)
    savedTrips.value = {}
    Message.success('会话已删除')
  } catch (error) {
    Message.error('删除失败，请重试')
  }
}

const scrollToBottom = () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

onMounted(async () => {
  narrowQuery = window.matchMedia('(max-width: 860px)')
  isNarrow.value = narrowQuery.matches
  narrowQuery.addEventListener('change', onBreakpointChange)

  try {
    const conversations = await conversationStore.fetchConversations()
    // 默认接着最近一段会话继续，避免每次进来都是一片空白
    if (conversations.length) {
      await conversationStore.selectConversation(conversations[0].id)
    }  } catch (error) {
    // 未登录或加载失败时保持空白状态
  }
  scrollToBottom()
})

onUnmounted(() => {
  narrowQuery?.removeEventListener('change', onBreakpointChange)
  stopTicker()
})
</script>

<style scoped>
/* 两列网格：左列会话栏（跨满全高），右列聊天内容。
   用网格而非嵌套 wrapper，是为了让会话栏与输入框同高、且各自独立滚动。 */
.chat-page {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  /* 撑满 sheet-content 的内容框（页头与页脚之间），而不是减去一个估算值：
     这样输入框稳定贴在底部，不会浮在半空、下方留一段空白 */
  height: 100%;
  /* 关键：这里**不能**设 min-height。
     页头 + 本页 + 页脚一旦超过视口，浏览器就会开始滚动整个文档，
     于是侧边栏和聊天区会「一起被滚走」——看起来就像两个面板滚动联动。
     让本页永远不超过可用高度，滚动就只会发生在各自的内部容器里。 */
  overflow: hidden;
}

.chat-side {
  grid-area: 1 / 1 / -1 / 2;
  /* 会话栏跨满四行，高度等于本页高度；列表再长也只在自己内部滚动 */
  min-height: 0;
}

/* 没有消息时，中间的空档由 chat-log 吸收，示例与输入框各归两端 */
.chat-page--empty .chat-log {
  padding-bottom: 0;
}

.chat-head {
  grid-area: 1 / 2;
  padding-top: 26px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--rule-strong);
}

/* 窄屏工具栏：会话栏进了抽屉，这里留出入口 */
.chat-head-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.rail-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px;
  border: 1px solid var(--rule-strong);
  background: var(--plot);
  color: var(--ink);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.rail-btn:hover {
  color: var(--magenta);
  border-color: var(--magenta);
}

/* ————————————————————————— 窄屏抽屉 ————————————————————————— */

.drawer-layer {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
}

.drawer-mask {
  position: absolute;
  inset: 0;
  background: rgba(14, 27, 34, 0.3);
}

.drawer-layer :deep(.side) {
  position: relative;
  z-index: 1;
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
  grid-area: 2 / 2;
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
  grid-area: 3 / 2;
  overflow-y: auto;
  min-height: 0;
  /* 滚到尽头后不要继续把滚动传给外层页面，否则会「连带」着滚另一个面板 */
  overscroll-behavior: contain;
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

/* ————————————————————————— 执行过程 ————————————————————————— */

/* 消息里的执行过程默认收起，展开后与「本轮调用」保持同样的左缩进 */
.steps-in-message {
  margin-bottom: 16px;
}

.calls-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  padding: 2px 8px;
  font-size: 12px;
  font-family: inherit;
  color: var(--ink-3);
  background: transparent;
  border: 1px solid var(--rule);
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.calls-toggle:hover {
  color: var(--ink);
  border-color: var(--rule-strong);
}

.calls-toggle-num {
  color: var(--ink-3);
}

/* ————————————————————————— 输入 ————————————————————————— */

.composer {
  grid-area: 4 / 2;
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
  justify-content: flex-end;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--rule);
}

@media (max-width: 860px) {
  /* 窄屏会话栏进了抽屉，聊天区回到单列 */
  .chat-page {
    height: auto;
    min-height: 0;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto auto auto auto;
  }

  .chat-head,
  .samples,
  .chat-log,
  .composer {
    grid-column: 1;
  }

  .chat-head {
    padding-top: 18px;
  }

  .chat-log {
    overflow: visible;
    padding-right: 0;
  }

  .entry {
    gap: 12px;
  }
}

/* 矮窗口：竖向空间紧张时，先把装饰性文案和留白让给对话区。
   窗口高度恢复后自动还原，不影响常规桌面下的排版。 */
@media (max-height: 780px) {
  .chat-head {
    padding-top: 14px;
    padding-bottom: 10px;
  }

  .chat-lede {
    display: none;
  }

  .composer {
    padding: 8px;
  }

  .composer-actions {
    margin-top: 8px;
    padding-top: 8px;
  }
}
</style>

<template>
  <div class="trip-detail-page">
    <a-spin :loading="loading" style="width: 100%">
      <a-result
        v-if="!loading && !trip"
        status="404"
        title="行程不存在"
        subtitle="该行程可能已被删除，或你没有访问权限"
      >
        <template #extra>
          <a-button type="primary" @click="$router.push('/plan')">返回我的规划</a-button>
        </template>
      </a-result>

      <template v-else-if="trip">
        <!-- 行程概览 -->
        <a-card class="trip-overview">
          <div class="overview-header">
            <div class="trip-info">
              <h1>{{ trip.title }}</h1>
              <div class="trip-meta">
                <span><icon-environment /> {{ trip.destination }}</span>
                <span><icon-calendar /> {{ trip.start_date }} ~ {{ trip.end_date }}</span>
                <span><icon-team /> {{ trip.travelers }} 人</span>
                <span v-if="trip.budget"><icon-money /> ¥{{ trip.budget.toLocaleString() }}</span>
              </div>
            </div>
            <div class="trip-actions">
              <a-tag :color="statusColor">{{ trip.status }}</a-tag>
              <a-button @click="$router.push('/ai-chat')">
                <template #icon><icon-robot /></template>
                让 AI 完善行程
              </a-button>
            </div>
          </div>
        </a-card>

        <!-- 天气（来自高德地图天气接口，由 AI 对话写入 generated_plan） -->
        <WeatherCard :weather="weather" class="mt" />

        <!-- 每日行程 -->
        <a-card v-if="days.length" title="🗓 每日行程" class="mt">
          <DayCard v-for="day in days" :key="day.id" :day="day" />
        </a-card>

        <!-- 行程地图 -->
        <a-card v-if="mapPoints.length" title="📍 行程地图" class="mt">
          <ItineraryMap :points="mapPoints" />
        </a-card>

        <!-- 规划详情（AI 生成的 Markdown） -->
        <a-card v-if="planContent" title="📝 规划详情" class="mt">
          <div class="markdown-content" v-html="renderMarkdown(planContent)"></div>
        </a-card>

        <!-- 无内容时给出明确指引，而不是填充示例数据 -->
        <a-empty
          v-if="!planContent && !days.length"
          class="mt"
          description="该行程还没有 AI 生成的内容"
        >
          <a-button type="primary" @click="$router.push('/ai-chat')">
            去智能规划
          </a-button>
        </a-empty>

        <a-alert type="info" class="mt" :show-icon="true">
          酒店与路线信息由 AI 在对话中实时查询（高德地图）。公开接口仅支持查询参考，
          无法直接完成在线下单预订，实际预订请通过酒店官方渠道或 OTA 平台完成。
        </a-alert>
      </template>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import WeatherCard from '../components/common/WeatherCard.vue'
import DayCard from '../components/trip/DayCard.vue'
import ItineraryMap from '../components/map/ItineraryMap.vue'
import { tripApi, type Trip } from '../api/trips'
import type { ItineraryDay, MapPoint, WeatherInfo } from '../types'

const route = useRoute()

const loading = ref(false)
const trip = ref<Trip | null>(null)

/** 后端生成的规划内容（真实数据，未生成时为空） */
const plan = computed<Record<string, any>>(() => trip.value?.generated_plan || {})

const weather = computed<WeatherInfo | undefined>(() => plan.value.weather_info)

const planContent = computed<string>(() => plan.value.content || '')

const days = computed<ItineraryDay[]>(() => plan.value.days || [])

const mapPoints = computed<MapPoint[]>(() =>
  (plan.value.spots || [])
    .filter((s: any) => s.longitude != null && s.latitude != null)
    .map((s: any) => ({
      name: s.name,
      lng: Number(s.longitude),
      lat: Number(s.latitude),
    }))
)

const statusColor = computed(() => {
  const map: Record<string, string> = {
    planning: 'blue',
    confirmed: 'green',
    in_progress: 'orange',
    completed: 'gray',
    cancelled: 'red',
  }
  return map[trip.value?.status || ''] || 'blue'
})

function renderMarkdown(content: string) {
  return content
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/\n/g, '<br>')
}

onMounted(async () => {
  const id = String(route.params.id || '')
  if (!id) return
  loading.value = true
  try {
    trip.value = await tripApi.detail(id)
  } catch {
    trip.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.trip-detail-page {
  padding-bottom: 24px;
}

.trip-overview {
  margin-bottom: 16px;
}

.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.trip-info h1 {
  font-size: 24px;
  margin-bottom: 8px;
}

.trip-meta {
  display: flex;
  gap: 24px;
  color: #86909c;
  flex-wrap: wrap;
}

.trip-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.trip-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mt {
  margin-top: 16px;
}

.markdown-content :deep(h2) {
  font-size: 18px;
  margin: 12px 0 8px;
}

.markdown-content :deep(li) {
  margin-left: 18px;
}
</style>

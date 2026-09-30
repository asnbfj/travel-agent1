<template>
  <div class="trip-plan-page">
    <div class="page-header">
      <h1>📋 我的旅行规划</h1>
      <a-button type="primary" @click="$router.push('/trip/create')">
        <template #icon><icon-plus /></template>
        新建行程
      </a-button>
    </div>

    <a-spin :loading="tripStore.loading" style="width: 100%">
      <a-empty
        v-if="!tripStore.trips.length"
        description="还没有行程，先创建或让 AI 帮你规划吧"
      >
        <a-button type="primary" @click="$router.push('/ai-chat')">去智能规划</a-button>
      </a-empty>

      <div v-else class="plan-layout">
        <!-- 行程列表 -->
        <aside class="trip-list">
          <div
            v-for="t in tripStore.trips"
            :key="t.id"
            :class="['trip-item', { active: t.id === selectedId }]"
            @click="selectTrip(t.id)"
          >
            <div class="trip-item-title">{{ t.title }}</div>
            <div class="trip-item-meta">{{ t.destination }} · {{ t.travelers }}人</div>
          </div>
        </aside>

        <!-- 详情内容 -->
        <main class="plan-content">
          <template v-if="currentTrip">
            <a-card class="overview">
              <div class="overview-header">
                <div>
                  <h2>{{ currentTrip.title }}</h2>
                  <div class="overview-meta">
                    <span><icon-environment /> {{ currentTrip.destination }}</span>
                    <span><icon-calendar /> {{ currentTrip.start_date }} ~ {{ currentTrip.end_date }}</span>
                    <span><icon-team /> {{ currentTrip.travelers }} 人</span>
                    <span><icon-money /> ¥{{ currentTrip.budget?.toLocaleString() }}</span>
                  </div>
                </div>
                <a-tag color="blue">{{ currentTrip.status }}</a-tag>
              </div>
            </a-card>

            <WeatherCard :weather="weather" class="mt" />

            <a-card title="📍 行程地图" class="mt">
              <ItineraryMap :points="mapPoints" />
            </a-card>

            <a-card v-if="days.length" title="🗓 每日行程" class="mt">
              <DayCard v-for="day in days" :key="day.id" :day="day" />
            </a-card>

            <a-card v-if="planContent" title="📝 规划详情" class="mt">
              <div class="markdown-content" v-html="renderMarkdown(planContent)"></div>
            </a-card>
          </template>
        </main>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import WeatherCard from '../components/common/WeatherCard.vue'
import DayCard from '../components/trip/DayCard.vue'
import ItineraryMap from '../components/map/ItineraryMap.vue'
import { useTripStore } from '../stores/trip'
import type { ItineraryDay, MapPoint, WeatherInfo } from '../types'

const tripStore = useTripStore()
const selectedId = ref<string>('')

const currentTrip = computed(() => tripStore.currentTrip)

const plan = computed<Record<string, any>>(() => currentTrip.value?.generated_plan || {})

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
    })),
)

async function selectTrip(id: string) {
  selectedId.value = id
  await tripStore.fetchTrip(id)
}

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
  await tripStore.fetchTrips().catch(() => {})
  if (tripStore.trips.length) {
    await selectTrip(tripStore.trips[0].id)
  }
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
}

.plan-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 16px;
  align-items: start;
}

.trip-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trip-item {
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s;
}

.trip-item:hover {
  border-color: #165dff;
}

.trip-item.active {
  border-color: #165dff;
  box-shadow: 0 2px 8px rgba(22, 93, 255, 0.15);
}

.trip-item-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.trip-item-meta {
  font-size: 12px;
  color: #86909c;
}

.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.overview-header h2 {
  margin: 0 0 8px;
}

.overview-meta {
  display: flex;
  gap: 24px;
  color: #86909c;
  font-size: 13px;
  flex-wrap: wrap;
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

@media (max-width: 900px) {
  .plan-layout {
    grid-template-columns: 1fr;
  }
}
</style>

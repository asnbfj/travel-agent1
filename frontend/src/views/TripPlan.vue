<template>
  <div class="plan-page">
    <header class="page-head plan-head">
      <div>
        <h1>我的行程</h1>
        <p class="lede">左边选一份行程，右边看它的时刻表、地图和规划原文。</p>
      </div>
      <a-button type="primary" @click="$router.push('/trip/create')">
        <template #icon><icon-plus /></template>
        新建行程
      </a-button>
    </header>

    <a-spin :loading="tripStore.loading" style="width: 100%">
      <div v-if="!tripStore.trips.length" class="empty">
        <p>还没有行程。让 AI 排一份，或者自己填一张表。</p>
        <a-button type="primary" @click="$router.push('/ai-chat')">去智能规划</a-button>
      </div>

      <div v-else class="plan-layout">
        <!-- 行程清单 -->
        <aside class="trip-list">
          <div class="list-head">共 {{ tripStore.trips.length }} 份</div>
          <button
            v-for="t in tripStore.trips"
            :key="t.id"
            type="button"
            :class="['trip-item', { 'trip-item--active': t.id === selectedId }]"
            @click="selectTrip(t.id)"
          >
            <span class="ti-title">{{ t.title }}</span>
            <span class="ti-meta num">{{ t.destination }}</span>
            <span class="ti-meta num">
              {{ formatMonthDay(t.start_date) }} – {{ formatMonthDay(t.end_date) }}
            </span>
          </button>
        </aside>

        <!-- 详情 -->
        <main class="plan-content">
          <template v-if="currentTrip">
            <header class="titleblock">
              <div class="tb-main">
                <h2 class="title-song">{{ currentTrip.title }}</h2>
                <dl class="tb-meta">
                  <div class="tb-item">
                    <dt>目的地</dt>
                    <dd>{{ currentTrip.destination }}</dd>
                  </div>
                  <div class="tb-item">
                    <dt>日期</dt>
                    <dd class="num">
                      {{ formatDateRange(currentTrip.start_date, currentTrip.end_date) }}
                      <span v-if="dayCount" class="tb-sub">共 {{ dayCount }} 天</span>
                    </dd>
                  </div>
                  <div class="tb-item">
                    <dt>同行</dt>
                    <dd class="num">{{ currentTrip.travelers }} 人</dd>
                  </div>
                  <div v-if="currentTrip.budget" class="tb-item">
                    <dt>预算</dt>
                    <dd class="num">¥{{ currentTrip.budget.toLocaleString() }}</dd>
                  </div>
                </dl>
              </div>
              <div class="tb-side">
                <span
                  class="status"
                  :class="`status--${tripStatusTone(currentTrip.status)}`"
                >
                  {{ tripStatusLabel(currentTrip.status) }}
                </span>
                <a-button size="small" @click="$router.push(`/trip/${currentTrip.id}`)">
                  打开详情页
                </a-button>
              </div>
            </header>

            <WeatherCard :weather="weather" class="stack" />

            <section v-if="mapPoints.length" class="plot stack">
              <div class="plot-label tick-cross">
                <span class="plot-label-name">行程地图</span>
                <span>{{ mapPoints.length }} 个坐标点</span><span>按顺序连线</span>
              </div>
              <div class="plot-body">
                <ItineraryMap :points="mapPoints" />
              </div>
            </section>

            <section v-if="days.length" class="plot stack">
              <div class="plot-label tick-cross">
                <span class="plot-label-name">每日行程</span>
                <span>{{ days.length }} 天</span><span>{{ spotCount }} 个停留点</span>
              </div>
              <div class="plot-body">
                <DayCard v-for="day in days" :key="day.id" :day="day" />
              </div>
            </section>

            <section v-if="planContent" class="plot stack">
              <div class="plot-label tick-cross">
                <span class="plot-label-name">规划详情</span>
                <span>AI 写下的原文</span>
              </div>
              <div class="plot-body">
                <div class="markdown-content" v-html="renderMarkdown(planContent)"></div>
              </div>
            </section>

            <div v-if="!planContent && !days.length" class="empty stack">
              <p>这份行程还没有 AI 生成的内容，只有基本信息。</p>
              <a-button type="primary" @click="$router.push('/ai-chat')">去智能规划</a-button>
            </div>
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
import {
  formatDateRange,
  formatMonthDay,
  tripStatusLabel,
  tripStatusTone,
  tripDays,
} from '../utils/labels'
import { renderMarkdown } from '../utils/markdown'
import type { ItineraryDay, MapPoint, WeatherInfo } from '../types'

const tripStore = useTripStore()
const selectedId = ref<string>('')

const currentTrip = computed(() => tripStore.currentTrip)

const plan = computed<Record<string, any>>(() => currentTrip.value?.generated_plan || {})

const weather = computed<WeatherInfo | undefined>(() => plan.value.weather_info)

const planContent = computed<string>(() => plan.value.content || '')

const days = computed<ItineraryDay[]>(() => plan.value.days || [])

const dayCount = computed(() =>
  tripDays(currentTrip.value?.start_date, currentTrip.value?.end_date),
)

const spotCount = computed(() =>
  days.value.reduce((sum, d) => sum + (d.spots?.length || 0), 0),
)

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


onMounted(async () => {
  await tripStore.fetchTrips().catch(() => {})
  if (tripStore.trips.length) {
    await selectTrip(tripStore.trips[0].id)
  }
})
</script>

<style scoped>
.plan-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.plan-layout {
  display: grid;
  grid-template-columns: 264px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

/* ————————————————————————— 行程清单 ————————————————————————— */

.trip-list {
  border: 1px solid var(--rule);
  background: var(--plot);
}

.list-head {
  padding: 9px 14px;
  border-bottom: 1px solid var(--rule);
  background: var(--plot-2);
  font-size: 12px;
  color: var(--ink-3);
}

.trip-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 11px 14px;
  border: none;
  border-top: 1px solid var(--rule);
  border-left: 2px solid transparent;
  background: transparent;
  text-align: left;
  font: inherit;
  color: var(--ink);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.trip-item:first-of-type {
  border-top: none;
}

.trip-item:hover {
  background: var(--paper-2);
}

/* 当前选中的行程：左侧一道品红刻度 */
.trip-item--active {
  border-left-color: var(--magenta);
  background: var(--plot-2);
}

.ti-title {
  font-size: 14px;
  font-weight: 600;
}

.ti-meta {
  font-size: 12px;
  color: var(--ink-3);
}

/* ————————————————————————— 详情 ————————————————————————— */

.plan-content {
  min-width: 0;
}

.titleblock {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ink);
}

.titleblock h2 {
  font-size: 26px;
  letter-spacing: 0.02em;
}

.tb-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 30px;
  margin: 12px 0 0;
}

.tb-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.tb-item dt {
  font-size: 11px;
  color: var(--ink-3);
}

.tb-item dd {
  margin: 0;
  font-size: 13px;
}

.tb-side {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
  padding-top: 4px;
}

.empty {
  border: 1px solid var(--rule);
  background: var(--plot);
  padding: 40px 20px;
  text-align: center;
}

.empty p {
  margin: 0 0 14px;
  color: var(--ink-2);
}

@media (max-width: 980px) {
  .plan-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .trip-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .list-head {
    grid-column: 1 / -1;
  }

  .trip-item {
    border-left: none;
    border-top: 1px solid var(--rule);
  }

  .trip-item--active {
    box-shadow: inset 3px 0 0 var(--magenta);
  }
}
</style>

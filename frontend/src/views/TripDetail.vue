<template>
  <div class="trip-detail">
    <a-spin :loading="loading" style="width: 100%">
      <a-result
        v-if="!loading && !trip"
        status="404"
        title="这个行程找不到了"
        subtitle="它可能已被删除，或者不属于当前账号。"
      >
        <template #extra>
          <a-button type="primary" @click="$router.push('/plan')">返回我的行程</a-button>
        </template>
      </a-result>

      <template v-else-if="trip">
        <!-- 标题栏：像图幅右上角的图名与比例尺 -->
        <header class="titleblock">
          <div class="tb-main">
            <h1 class="title-song">{{ trip.title }}</h1>
            <dl class="tb-meta">
              <div class="tb-item">
                <dt>目的地</dt>
                <dd>{{ trip.destination }}</dd>
              </div>
              <div class="tb-item">
                <dt>日期</dt>
                <dd class="num">
                  {{ formatDateRange(trip.start_date, trip.end_date) }}
                  <span v-if="dayCount" class="tb-sub">共 {{ dayCount }} 天</span>
                </dd>
              </div>
              <div class="tb-item">
                <dt>同行</dt>
                <dd class="num">{{ trip.travelers }} 人</dd>
              </div>
              <div v-if="trip.budget" class="tb-item">
                <dt>预算</dt>
                <dd class="num">¥{{ trip.budget.toLocaleString() }}</dd>
              </div>
            </dl>
          </div>

          <div class="tb-side">
            <span class="status" :class="`status--${tripStatusTone(trip.status)}`">
              {{ tripStatusLabel(trip.status) }}
            </span>
            <a-button @click="$router.push('/ai-chat')">
              <template #icon><icon-robot /></template>
              让 AI 完善行程
            </a-button>
          </div>
        </header>

        <!-- 天气（来自高德地图天气接口，由 AI 对话写入 generated_plan） -->
        <WeatherCard :weather="weather" class="stack" />

        <!-- 每日行程 -->
        <section v-if="days.length" class="plot stack">
          <div class="plot-label tick-cross">
            <span class="plot-label-name">每日行程</span>
            <span>{{ days.length }} 天</span><span>{{ spotCount }} 个停留点</span>
          </div>
          <div class="plot-body">
            <DayCard v-for="day in days" :key="day.id" :day="day" />
          </div>
        </section>

        <!-- 行程地图 -->
        <section v-if="mapPoints.length" class="plot stack">
          <div class="plot-label tick-cross">
            <span class="plot-label-name">行程地图</span>
            <span>{{ mapPoints.length }} 个坐标点</span><span>按顺序连线</span>
          </div>
          <div class="plot-body">
            <ItineraryMap :points="mapPoints" />
          </div>
        </section>

        <!-- 规划详情（AI 生成的 Markdown） -->
        <section v-if="planContent" class="plot stack">
          <div class="plot-label tick-cross">
            <span class="plot-label-name">规划详情</span>
            <span>AI 写下的原文</span>
          </div>
          <div class="plot-body">
            <div class="markdown-content" v-html="renderMarkdown(planContent)"></div>
          </div>
        </section>

        <!-- 无内容时给出明确指引，而不是填充示例数据 -->
        <div v-if="!planContent && !days.length" class="empty stack">
          <p>这份行程还没有 AI 生成的内容，只有基本信息。</p>
          <a-button type="primary" @click="$router.push('/ai-chat')">去智能规划</a-button>
        </div>

        <section class="note stack">
          <div class="note-label">预订说明</div>
          <p>
            酒店与路线信息由 AI 在对话中实时查询（高德地图）。公开接口只能查询参考，
            无法直接完成在线下单，实际预订请通过酒店官方渠道或 OTA 平台完成。
          </p>
        </section>
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
import { formatDateRange, tripStatusLabel, tripStatusTone, tripDays } from '../utils/labels'
import { renderMarkdown } from '../utils/markdown'
import type { ItineraryDay, MapPoint, WeatherInfo } from '../types'

const route = useRoute()

const loading = ref(false)
const trip = ref<Trip | null>(null)

/** 后端生成的规划内容（真实数据，未生成时为空） */
const plan = computed<Record<string, any>>(() => trip.value?.generated_plan || {})

const weather = computed<WeatherInfo | undefined>(() => plan.value.weather_info)

const planContent = computed<string>(() => plan.value.content || '')

const days = computed<ItineraryDay[]>(() => plan.value.days || [])

const dayCount = computed(() => tripDays(trip.value?.start_date, trip.value?.end_date))

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
    }))
)


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
.trip-detail {
  padding-top: 30px;
}

/* ————————————————————————— 标题栏 ————————————————————————— */

.titleblock {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--ink);
}

.titleblock h1 {
  font-size: 32px;
  letter-spacing: 0.02em;
}

.tb-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 34px;
  margin: 14px 0 0;
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
  font-size: 14px;
  color: var(--ink);
}

.tb-side {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
  padding-top: 4px;
}

/* ————————————————————————— 说明 ————————————————————————— */

.empty {
  border: 1px solid var(--rule);
  background: var(--plot);
  padding: 30px 20px;
  text-align: center;
}

.empty p {
  margin: 0 0 14px;
  color: var(--ink-2);
}

.note {
  border: 1px solid var(--rule);
  border-left: 3px solid var(--rule-strong);
  background: var(--plot-2);
  padding: 14px 16px;
}

.note-label {
  font-size: 12px;
  color: var(--ink-3);
  margin-bottom: 4px;
}

.note p {
  margin: 0;
  font-size: 13px;
  color: var(--ink-2);
  max-width: 84ch;
}

@media (max-width: 860px) {
  .titleblock {
    flex-direction: column;
    gap: 14px;
  }

  .titleblock h1 {
    font-size: 26px;
  }

  .tb-side {
    padding-top: 0;
  }
}
</style>

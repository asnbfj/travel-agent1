<template>
  <div class="home-page">
    <!-- Hero -->
    <section class="hero">
      <h1>TravelAI · 智能旅行规划</h1>
      <p class="hero-sub">
        基于 LLM · Agent · RAG · LangGraph 的自主决策旅行规划系统，
        用自然语言描述需求，AI 自动生成完整攻略。
      </p>
      <div class="hero-actions">
        <a-button type="primary" size="large" @click="go('/ai-chat')">
          <template #icon><icon-robot /></template>
          开始智能规划
        </a-button>
        <a-button size="large" @click="go('/trip/create')">
          <template #icon><icon-plus /></template>
          手动创建行程
        </a-button>
      </div>
    </section>

    <!-- 能力 -->
    <section class="features">
      <a-card v-for="f in features" :key="f.title" class="feature-card" :bordered="false">
        <div class="feature-icon">{{ f.icon }}</div>
        <div class="feature-title">{{ f.title }}</div>
        <div class="feature-desc">{{ f.desc }}</div>
      </a-card>
    </section>

    <!-- 我的行程 -->
    <section class="my-trips" v-if="auth.isLoggedIn">
      <div class="section-header">
        <h2>我的行程</h2>
        <a-link @click="go('/plan')">查看全部</a-link>
      </div>
      <a-empty v-if="!tripStore.trips.length" description="还没有行程，快去创建一个吧" />
      <div v-else class="trip-grid">
        <a-card
          v-for="trip in tripStore.trips.slice(0, 3)"
          :key="trip.id"
          :hoverable="true"
          class="trip-card"
          @click="go(`/trip/${trip.id}`)"
        >
          <div class="trip-card-title">{{ trip.title }}</div>
          <div class="trip-card-meta">
            <span><icon-environment /> {{ trip.destination }}</span>
            <span><icon-calendar /> {{ trip.start_date }} ~ {{ trip.end_date }}</span>
          </div>
          <a-tag size="small" :color="statusColor(trip.status)">{{ trip.status }}</a-tag>
        </a-card>
      </div>
    </section>

    <!-- 架构说明 -->
    <section class="arch">
      <h2>Agent 工作流</h2>
      <a-steps :current="6" class="arch-steps">
        <a-step v-for="s in workflow" :key="s" :title="s" />
      </a-steps>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useTripStore } from '../stores/trip'

const router = useRouter()
const auth = useAuthStore()
const tripStore = useTripStore()

const features = [
  { icon: '🎯', title: '智能行程规划', desc: '基于偏好与预算自动生成最优路线' },
  { icon: '🤖', title: '多阶段规划工作流', desc: '目的地研究 → 景点筛选 → 行程编排 → 优化调整' },
  { icon: '📚', title: '知识增强 RAG', desc: '融合景点知识库、旅游攻略与实时天气' },
  { icon: '🔄', title: '灵活调整', desc: '随时修改行程、增删景点、调整时间' },
]

const workflow = ['解析需求', '景点检索', '天气查询', '行程编排', '路线优化', '生成攻略']

function go(path: string) {
  router.push(path)
}

function statusColor(status: string) {
  const map: Record<string, string> = {
    planning: 'blue',
    confirmed: 'green',
    in_progress: 'orange',
    completed: 'gray',
    cancelled: 'red',
  }
  return map[status] || 'gray'
}

onMounted(() => {
  if (auth.isLoggedIn) {
    tripStore.fetchTrips().catch(() => {})
  }
})
</script>

<style scoped>
.hero {
  text-align: center;
  padding: 48px 0 32px;
}

.hero h1 {
  font-size: 36px;
  margin-bottom: 16px;
}

.hero-sub {
  color: #86909c;
  max-width: 640px;
  margin: 0 auto 24px;
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.features {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 32px 0;
}

.feature-card {
  text-align: center;
}

.feature-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.feature-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.feature-desc {
  font-size: 12px;
  color: #86909c;
}

.my-trips {
  margin: 40px 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.trip-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.trip-card {
  cursor: pointer;
}

.trip-card-title {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: 8px;
}

.trip-card-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #86909c;
  margin-bottom: 8px;
}

.arch {
  margin-top: 40px;
}

.arch h2 {
  text-align: center;
  margin-bottom: 24px;
}

.arch-steps {
  max-width: 900px;
  margin: 0 auto;
}

@media (max-width: 900px) {
  .features,
  .trip-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>

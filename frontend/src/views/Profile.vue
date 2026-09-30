<template>
  <div class="profile-page">
    <header class="page-head">
      <h1>我的</h1>
      <p class="lede">账号信息、行程数量和规划偏好都存在这里。</p>
    </header>

    <!-- 账号 -->
    <section class="plot">
      <div class="plot-label tick-cross">
        <span class="plot-label-name">账号</span>
      </div>
      <div class="plot-body account">
        <div class="account-main">
          <div class="account-name">
            <h2>{{ auth.user?.username || '未登录' }}</h2>
            <span class="account-email">{{ auth.user?.email || '—' }}</span>
          </div>
          <dl class="account-meta">
            <div class="meta-item">
              <dt>规划偏好</dt>
              <dd>{{ riskLevelLabel(auth.user?.risk_level) }}</dd>
            </div>
          </dl>
        </div>
        <a-button v-if="auth.isLoggedIn" @click="logout">
          <template #icon><icon-export /></template>
          退出登录
        </a-button>
      </div>
    </section>

    <!-- 行程数量：标签与数字成列，不做大数字卡片 -->
    <section class="plot stack">
      <div class="plot-label tick-cross">
        <span class="plot-label-name">行程数量</span>
        <span>{{ tripStore.trips.length }} 份</span>
      </div>
      <dl class="count-list">
        <div v-for="s in stats" :key="s.label" class="count-row">
          <dt>{{ s.label }}</dt>
          <dd class="num">{{ s.value }}</dd>
        </div>
      </dl>
    </section>

    <!-- 偏好 -->
    <section class="plot stack">
      <div class="plot-label tick-cross">
        <span class="plot-label-name">旅行偏好</span>
        <span>下次规划时会带上这些条件</span>
      </div>
      <div class="plot-body">
        <a-form layout="vertical" :model="preferences">
          <a-form-item label="偏好风格">
            <a-select v-model="preferences.travel_style">
              <a-option v-for="s in styles" :key="s.value" :value="s.value">
                {{ s.label }}
              </a-option>
            </a-select>
          </a-form-item>

          <a-form-item label="饮食偏好">
            <a-checkbox-group v-model="preferences.diet">
              <a-checkbox value="local">当地特色</a-checkbox>
              <a-checkbox value="vegetarian">素食</a-checkbox>
              <a-checkbox value="halal">清真</a-checkbox>
              <a-checkbox value="no-spicy">不吃辣</a-checkbox>
            </a-checkbox-group>
          </a-form-item>

          <a-form-item label="备注">
            <a-textarea
              v-model="preferences.notes"
              placeholder="例如：每天最多三个景点，尽量少走路"
              :auto-size="{ minRows: 2, maxRows: 4 }"
            />
          </a-form-item>

          <a-button type="primary" @click="savePreferences">保存偏好</a-button>
        </a-form>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { useAuthStore } from '../stores/auth'
import { useTripStore } from '../stores/trip'
import { riskLevelLabel, travelStyleLabel } from '../utils/labels'

const router = useRouter()
const auth = useAuthStore()
const tripStore = useTripStore()

const styles = [
  { label: '休闲度假', value: 'relaxed' },
  { label: '文化探索', value: 'cultural' },
  { label: '亲子游', value: 'family' },
  { label: '美食之旅', value: 'foodie' },
  { label: '摄影采风', value: 'photography' },
]

const preferences = reactive({
  travel_style: 'relaxed',
  diet: ['local'],
  notes: '',
})

const stats = computed(() => [
  { label: '全部行程', value: tripStore.trips.length },
  { label: '规划中', value: tripStore.trips.filter((t) => t.status === 'planning').length },
  { label: '已完成', value: tripStore.trips.filter((t) => t.status === 'completed').length },
])

const styleSummary = computed(() => travelStyleLabel(preferences.travel_style))

function logout() {
  auth.logout()
  Message.success('已退出登录')
  router.push('/')
}

function savePreferences() {
  localStorage.setItem('preferences', JSON.stringify(preferences))
  Message.success(`偏好已保存：${styleSummary.value}`)
}

onMounted(async () => {
  const saved = localStorage.getItem('preferences')
  if (saved) Object.assign(preferences, JSON.parse(saved))
  await tripStore.fetchTrips().catch(() => {})
})
</script>

<style scoped>
.profile-page {
  max-width: 760px;
}

.account {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.account-name {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.account-name h2 {
  font-family: var(--font-song);
  font-size: 22px;
  font-weight: 700;
}

.account-email {
  font-size: 13px;
  color: var(--ink-3);
}

.account-meta {
  display: flex;
  gap: 30px;
  margin: 12px 0 0;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.meta-item dt {
  font-size: 11px;
  color: var(--ink-3);
}

.meta-item dd {
  margin: 0;
  font-size: 14px;
}

/* 数量清单：标签在左、数字在右，成列可扫读 */
.count-list {
  margin: 0;
}

.count-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding: 11px 16px;
  border-top: 1px solid var(--rule);
}

.count-row:first-child {
  border-top: none;
}

.count-row dt {
  font-size: 14px;
  color: var(--ink-2);
}

.count-row dd {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ink);
}

@media (max-width: 640px) {
  .account {
    flex-direction: column;
  }
}
</style>

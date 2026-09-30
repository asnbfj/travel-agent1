<template>
  <div class="profile-page">
    <a-card class="profile-card">
      <div class="profile-header">
        <a-avatar :size="64" class="avatar">
          <icon-user />
        </a-avatar>
        <div class="profile-info">
          <h2>{{ auth.user?.username || '未登录' }}</h2>
          <div class="email">{{ auth.user?.email || '—' }}</div>
          <a-tag size="small" color="arcoblue">
            风险偏好：{{ auth.user?.risk_level || 'moderate' }}
          </a-tag>
        </div>
        <a-button v-if="auth.isLoggedIn" status="danger" @click="logout">
          <template #icon><icon-export /></template>
          退出登录
        </a-button>
      </div>
    </a-card>

    <div class="stat-grid">
      <a-card v-for="s in stats" :key="s.label" class="stat-card" :bordered="false">
        <div class="stat-value">{{ s.value }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </a-card>
    </div>

    <a-card title="⚙ 旅行偏好" class="pref-card">
      <a-form layout="vertical" :model="preferences">
        <a-form-item label="偏好风格">
          <a-select v-model="preferences.travel_style">
            <a-option v-for="s in styles" :key="s.value" :value="s.value">{{ s.label }}</a-option>
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
          <a-textarea v-model="preferences.notes" :auto-size="{ minRows: 2, maxRows: 4 }" />
        </a-form-item>
        <a-button type="primary" @click="savePreferences">保存偏好</a-button>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { useAuthStore } from '../stores/auth'
import { useTripStore } from '../stores/trip'

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
  { label: '行程总数', value: tripStore.trips.length },
  { label: '规划中', value: tripStore.trips.filter((t) => t.status === 'planning').length },
  { label: '已完成', value: tripStore.trips.filter((t) => t.status === 'completed').length },
])

function logout() {
  auth.logout()
  Message.success('已退出登录')
  router.push('/')
}

function savePreferences() {
  Message.success('偏好已保存到本地（后端接口可扩展持久化）')
  localStorage.setItem('preferences', JSON.stringify(preferences))
}

onMounted(async () => {
  const saved = localStorage.getItem('preferences')
  if (saved) Object.assign(preferences, JSON.parse(saved))
  await tripStore.fetchTrips().catch(() => {})
})
</script>

<style scoped>
.profile-page {
  max-width: 800px;
  margin: 0 auto;
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.avatar {
  background: #165dff;
}

.profile-info {
  flex: 1;
}

.profile-info h2 {
  margin: 0 0 4px;
}

.email {
  color: #86909c;
  font-size: 13px;
  margin-bottom: 8px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin: 16px 0;
}

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #165dff;
}

.stat-label {
  font-size: 12px;
  color: #86909c;
}
</style>

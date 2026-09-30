<template>
  <header class="app-header">
    <div class="header-inner">
      <router-link to="/" class="logo">
        <span class="logo-icon">🧳</span>
        <span class="logo-text">TravelAI</span>
      </router-link>

      <nav class="nav">
        <router-link to="/" class="nav-item">首页</router-link>
        <router-link to="/ai-chat" class="nav-item">智能规划</router-link>
        <router-link to="/plan" class="nav-item">我的行程</router-link>
        <router-link to="/profile" class="nav-item">我的</router-link>
      </nav>

      <div class="actions">
        <template v-if="auth.isLoggedIn">
          <a-dropdown>
            <a-avatar :size="32" class="avatar">
              <icon-user />
            </a-avatar>
            <template #content>
              <a-doption disabled>{{ auth.user?.username || '用户' }}</a-doption>
              <a-doption @click="auth.logout()">
                <template #icon><icon-export /></template>
                退出登录
              </a-doption>
            </template>
          </a-dropdown>
        </template>
        <template v-else>
          <a-button type="primary" size="small" @click="openLogin">
            登录 / 注册
          </a-button>
        </template>
      </div>
    </div>

    <a-modal
      v-model:visible="visible"
      :title="mode === 'login' ? '登录 TravelAI' : '注册账号'"
      :footer="false"
      width="400px"
    >
      <a-form :model="form" layout="vertical" @submit-success="submit">
        <a-form-item field="username" label="用户名" :rules="[{ required: true }]">
          <a-input v-model="form.username" placeholder="请输入用户名" />
        </a-form-item>
        <a-form-item
          v-if="mode === 'register'"
          field="email"
          label="邮箱"
          :rules="[{ required: true, type: 'email' }]"
        >
          <a-input v-model="form.email" placeholder="请输入邮箱" />
        </a-form-item>
        <a-form-item field="password" label="密码" :rules="[{ required: true, minLength: 6 }]">
          <a-input-password v-model="form.password" placeholder="请输入密码（至少6位）" />
        </a-form-item>
        <a-button type="primary" long :loading="loading" @click="submit">
          {{ mode === 'login' ? '登录' : '注册并登录' }}
        </a-button>
        <div class="switch-mode">
          <a-link @click="mode = mode === 'login' ? 'register' : 'login'">
            {{ mode === 'login' ? '还没有账号？去注册' : '已有账号？去登录' }}
          </a-link>
        </div>
      </a-form>
    </a-modal>
  </header>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const visible = ref(false)
const mode = ref<'login' | 'register'>('login')
const loading = ref(false)
const form = reactive({ username: '', email: '', password: '' })

function openLogin() {
  mode.value = 'login'
  visible.value = true
}

watch(
  () => route.query.login,
  (val) => {
    if (val) {
      openLogin()
      router.replace({ query: {} })
    }
  },
  { immediate: true },
)

async function submit() {
  if (!form.username || !form.password) {
    Message.warning('请填写用户名和密码')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(form.username, form.password)
    } else {
      await auth.register(form.username, form.email, form.password)
    }
    Message.success('操作成功')
    visible.value = false
    form.username = ''
    form.email = ''
    form.password = ''
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    Message.error(detail || '操作失败，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.app-header {
  background: #fff;
  border-bottom: 1px solid #e5e6eb;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  height: 60px;
  display: flex;
  align-items: center;
  gap: 32px;
  padding: 0 24px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 18px;
}

.logo-icon {
  font-size: 22px;
}

.nav {
  display: flex;
  gap: 24px;
  flex: 1;
}

.nav-item {
  color: #4e5969;
  font-size: 14px;
  padding: 4px 0;
  border-bottom: 2px solid transparent;
}

.nav-item.router-link-exact-active {
  color: #165dff;
  border-bottom-color: #165dff;
  font-weight: 600;
}

.avatar {
  cursor: pointer;
  background: #165dff;
}

.switch-mode {
  margin-top: 12px;
  text-align: center;
}
</style>

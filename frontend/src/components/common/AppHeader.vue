<template>
  <header class="app-header">
    <div class="header-inner">
      <router-link to="/" class="logo">
        <!-- 航线标：起点为品红，终点为墨色 -->
        <svg class="logo-mark" viewBox="0 0 28 22" aria-hidden="true">
          <path d="M4 17 L11 8 L17 12 L24 3" fill="none" stroke="currentColor" stroke-width="1.3" />
          <circle cx="4" cy="17" r="2.6" class="logo-origin" />
          <circle cx="24" cy="3" r="1.7" fill="currentColor" />
        </svg>
        <span class="logo-lockup">
          <span class="logo-text">TravelAI</span>
          <span class="logo-cn title-song">旅行智脑</span>
        </span>
      </router-link>

      <nav class="nav">
        <router-link to="/" class="nav-item">首页</router-link>
        <router-link to="/ai-chat" class="nav-item">智能规划</router-link>
        <router-link to="/plan" class="nav-item">我的行程</router-link>
        <router-link to="/settings" class="nav-item">配置</router-link>
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
        </template>      </div>
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
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--plot);
  border-bottom: 1px solid var(--ink);
}

.header-inner {
  max-width: calc(var(--page-max) + var(--rail) * 2);
  margin: 0 auto;
  height: 62px;
  display: flex;
  align-items: center;
  gap: 36px;
  padding: 0 24px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--ink);
}

.logo-mark {
  width: 30px;
  height: 24px;
  flex: none;
  color: var(--ink);
}

.logo-origin {
  fill: var(--magenta);
}

.logo-lockup {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.logo-text {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.logo-cn {
  font-size: 13px;
  font-weight: 400;
  color: var(--ink-3);
}

.nav {
  display: flex;
  gap: 22px;
  flex: 1;
}

/* 当前页用一小段品红刻度标记，而不是整条下划线 */
.nav-item {
  position: relative;
  color: var(--ink-2);
  font-size: 14px;
  padding: 3px 0 6px;
  transition: color 0.15s ease;
}

.nav-item::after {
  content: '';
  position: absolute;
  left: 0;
  bottom: 0;
  width: 0;
  height: 2px;
  background: var(--magenta);
  transition: width 0.18s ease;
}

.nav-item:hover {
  color: var(--ink);
}

.nav-item.router-link-exact-active {
  color: var(--ink);
  font-weight: 600;
}

.nav-item.router-link-exact-active::after {
  width: 16px;
}

.avatar {
  cursor: pointer;
  background: var(--ink);
}

.switch-mode {
  margin-top: 12px;
  text-align: center;
}

@media (max-width: 860px) {
  .header-inner {
    gap: 16px;
    padding: 0 16px;
  }

  .nav {
    gap: 14px;
  }

  .logo-cn {
    display: none;
  }
}

/* 窄屏：导航不换行，放不下时横向滑动，而不是把字挤成竖排 */
@media (max-width: 640px) {
  .header-inner {
    height: 56px;
    gap: 12px;
    padding: 0 14px;
  }

  .nav {
    gap: 12px;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .nav::-webkit-scrollbar {
    display: none;
  }

  .nav-item {
    flex: none;
    font-size: 13px;
    white-space: nowrap;
  }

  .logo-text {
    font-size: 15px;
  }
}

@media (max-width: 420px) {
  .logo-text {
    display: none;
  }
}
</style>

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi, type UserInfo } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const user = ref<UserInfo | null>(
    JSON.parse(localStorage.getItem('user') || 'null'),
  )

  const isLoggedIn = computed(() => Boolean(token.value))

  function persist() {
    if (token.value) {
      localStorage.setItem('token', token.value)
    } else {
      localStorage.removeItem('token')
    }
    if (user.value) {
      localStorage.setItem('user', JSON.stringify(user.value))
    } else {
      localStorage.removeItem('user')
    }
  }

  async function login(username: string, password: string) {
    const res = await authApi.login({ username, password })
    token.value = res.access_token
    if (res.user) {
      user.value = res.user
    }
    persist()
    if (!user.value) {
      await fetchMe()
    }
    return res
  }

  async function register(username: string, email: string, password: string) {
    await authApi.register({ username, email, password })
    return login(username, password)
  }

  async function fetchMe() {
    try {
      user.value = await authApi.me()
      persist()
    } catch {
      user.value = null
    }
    return user.value
  }

  function logout() {
    token.value = ''
    user.value = null
    persist()
  }

  return { token, user, isLoggedIn, login, register, fetchMe, logout }
})

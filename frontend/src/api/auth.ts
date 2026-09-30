/**
 * 认证 API
 */
import { request } from './index'

export interface UserInfo {
  id: string
  username: string
  email: string
  avatar_url?: string
  preferences: Record<string, any>
  risk_level: string
  created_at: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user?: UserInfo
}

export const authApi = {
  register: (data: { username: string; email: string; password: string }) => {
    return request.post<UserInfo>('/api/v1/auth/register', data)
  },

  login: (data: { username: string; password: string }) => {
    const form = new FormData()
    form.append('username', data.username)
    form.append('password', data.password)
    return request.post<LoginResponse>('/api/v1/auth/login', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  me: () => {
    return request.get<UserInfo>('/api/v1/auth/me')
  },
}

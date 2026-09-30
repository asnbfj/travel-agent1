import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('../views/Home.vue'),
    meta: { title: '首页' },
  },
  {
    path: '/ai-chat',
    name: 'ai-chat',
    component: () => import('../views/AIChat.vue'),
    meta: { title: '智能规划', requiresAuth: true },
  },
  {
    path: '/trip/create',
    name: 'trip-create',
    component: () => import('../views/TripCreate.vue'),
    meta: { title: '创建行程', requiresAuth: true },
  },
  {
    path: '/trip/:id',
    name: 'trip-detail',
    component: () => import('../views/TripDetail.vue'),
    props: true,
    meta: { title: '行程详情' },
  },
  {
    path: '/plan',
    name: 'trip-plan',
    component: () => import('../views/TripPlan.vue'),
    meta: { title: '行程规划', requiresAuth: true },
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('../views/Profile.vue'),
    meta: { title: '我的', requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/Settings.vue'),
    meta: { title: '配置', requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to, _from, next) => {
  document.title = to.meta.title ? `${to.meta.title} · TravelAI` : 'TravelAI'
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    next({ name: 'home', query: { login: '1' } })
    return
  }
  next()
})

export default router

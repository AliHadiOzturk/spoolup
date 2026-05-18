import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true }
    },
    {
      path: '/',
      component: () => import('@/components/layout/AppShell.vue'),
      children: [
        {
          path: '',
          name: 'Dashboard',
          component: () => import('@/views/DashboardView.vue')
        },
        {
          path: '/videos',
          name: 'Videos',
          component: () => import('@/views/VideosView.vue')
        },
        {
          path: '/videos/:id',
          name: 'VideoDetail',
          component: () => import('@/views/VideoDetailView.vue')
        },
        {
          path: '/uploads',
          name: 'Uploads',
          component: () => import('@/views/UploadsView.vue')
        },
        {
          path: '/analytics',
          name: 'Analytics',
          component: () => import('@/views/AnalyticsView.vue')
        },
        {
          path: '/printers',
          name: 'Printers',
          component: () => import('@/views/PrintersView.vue')
        },
        {
          path: '/audio',
          name: 'Audio',
          component: () => import('@/views/AudioView.vue')
        },
        {
          path: '/settings',
          name: 'Settings',
          component: () => import('@/views/SettingsView.vue')
        }
      ]
    }
  ]
})

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()
  
  if (!authStore.initialized) {
    await authStore.fetchUser()
  }
  
  if (to.meta.public && authStore.isAuthenticated) {
    next('/')
  } else if (!to.meta.public && !authStore.isAuthenticated) {
    next('/login')
  } else {
    next()
  }
})

export default router
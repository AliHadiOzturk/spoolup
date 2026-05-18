<template>
  <aside
    :class="[
      'fixed inset-y-0 left-0 z-40 w-64 bg-surface border-r border-border transition-transform duration-300 ease-in-out lg:static lg:translate-x-0',
      uiStore.sidebarOpen ? 'translate-x-0' : '-translate-x-full'
    ]"
  >
    <div class="flex flex-col h-full">
      <!-- Logo -->
      <div class="flex items-center gap-3 px-6 h-16 border-b border-border">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
          <Play class="w-4 h-4 text-white" />
        </div>
        <span class="text-lg font-bold gradient-text">VMS</span>
      </div>
      
      <!-- Navigation -->
      <nav class="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          :class="[
            'nav-item',
            { active: $route.path === item.path || $route.path.startsWith(item.path + '/') }
          ]"
        >
          <component :is="item.icon" class="w-5 h-5" />
          <span>{{ item.name }}</span>
        </RouterLink>
      </nav>
      
      <!-- User section -->
      <div class="p-4 border-t border-border">
        <div class="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-elevated">
          <div class="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
            <User class="w-4 h-4 text-primary" />
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-text-primary truncate">
              {{ authStore.user?.username || 'User' }}
            </p>
          </div>
          <button
            @click="authStore.logout"
            class="p-1.5 rounded-lg text-text-muted hover:text-error hover:bg-error/10 transition-colors"
            title="Logout"
          >
            <LogOut class="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  </aside>
  
  <!-- Mobile overlay -->
  <div
    v-if="uiStore.sidebarOpen && uiStore.isMobile"
    class="fixed inset-0 bg-black/50 z-30 lg:hidden"
    @click="uiStore.toggleSidebar"
  />
</template>

<script setup lang="ts">
import { 
  LayoutDashboard, 
  Video, 
  Upload, 
  BarChart3, 
  Printer, 
  Music, 
  Settings,
  User,
  LogOut,
  Play
} from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'

const authStore = useAuthStore()
const uiStore = useUIStore()

const navItems = [
  { name: 'Dashboard', path: '/', icon: LayoutDashboard },
  { name: 'Videos', path: '/videos', icon: Video },
  { name: 'Uploads', path: '/uploads', icon: Upload },
  { name: 'Analytics', path: '/analytics', icon: BarChart3 },
  { name: 'Printers', path: '/printers', icon: Printer },
  { name: 'Audio', path: '/audio', icon: Music },
  { name: 'Settings', path: '/settings', icon: Settings },
]
</script>
<template>
  <header class="h-16 bg-surface/80 backdrop-blur-md border-b border-border flex items-center justify-between px-6 sticky top-0 z-30">
    <div class="flex items-center gap-4">
      <button
        @click="uiStore.toggleSidebar"
        class="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface-elevated transition-colors lg:hidden"
      >
        <Menu class="w-5 h-5" />
      </button>
      
      <!-- Breadcrumb -->
      <div class="hidden md:flex items-center gap-2 text-sm">
        <span class="text-text-muted">VMS</span>
        <ChevronRight class="w-4 h-4 text-text-muted" />
        <span class="text-text-primary font-medium">{{ pageTitle }}</span>
      </div>
    </div>
    
    <div class="flex items-center gap-3">
      <!-- Search -->
      <div class="relative hidden sm:block">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          type="text"
          placeholder="Search..."
          class="pl-9 pr-4 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/50 w-64"
        />
      </div>
      
      <!-- Notifications -->
      <button class="relative p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface-elevated transition-colors">
        <Bell class="w-5 h-5" />
        <span class="absolute top-1.5 right-1.5 w-2 h-2 bg-error rounded-full"></span>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Menu, ChevronRight, Search, Bell } from 'lucide-vue-next'
import { useUIStore } from '@/stores/ui'

const route = useRoute()
const uiStore = useUIStore()

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    'Dashboard': 'Dashboard',
    'Videos': 'Videos',
    'VideoDetail': 'Video Details',
    'Uploads': 'Upload Queue',
    'Analytics': 'Analytics',
    'Printers': 'Printers',
    'Audio': 'Audio Library',
    'Settings': 'Settings'
  }
  return titles[route.name as string] || 'Dashboard'
})
</script>
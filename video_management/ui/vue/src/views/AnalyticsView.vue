<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-text-primary">Analytics</h1>
        <p class="text-text-secondary mt-1">Track your video performance</p>
      </div>
      
      <div class="flex items-center gap-2">
        <select
          v-model="dateRange"
          class="px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
          @change="loadAnalytics"
        >
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
          <option value="90">Last 90 days</option>
        </select>
      </div>
    </div>
    
    <!-- Stats cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card
        v-for="stat in analyticsStats"
        :key="stat.name"
        class="p-6"
      >
        <div class="flex items-center justify-between mb-4">
          <div
            :class="[
              'w-10 h-10 rounded-lg flex items-center justify-center',
              stat.iconBg
            ]"
          >
            <component :is="stat.icon" :class="['w-5 h-5', stat.iconColor]" />
          </div>
        </div>
        
        <p class="text-2xl font-bold text-text-primary mb-1">{{ stat.value }}</p>
        <p class="text-sm text-text-secondary">{{ stat.name }}</p>
      </Card>
    </div>
    
    <!-- Charts -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card class="p-6">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Views Over Time</h2>
        <div class="h-64 bg-surface-elevated rounded-lg flex items-center justify-center">
          <div class="text-center">
            <TrendingUp class="w-12 h-12 text-text-muted mx-auto mb-2" />
            <p class="text-text-secondary text-sm">Analytics charts coming soon</p>
          </div>
        </div>
      </Card>
      
      <Card class="p-6">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Platform Performance</h2>
        <div class="h-64 bg-surface-elevated rounded-lg flex items-center justify-center">
          <div class="text-center">
            <BarChart3 class="w-12 h-12 text-text-muted mx-auto mb-2" />
            <p class="text-text-secondary text-sm">Analytics charts coming soon</p>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Eye,
  ThumbsUp,
  MessageCircle,
  Share2,
  TrendingUp,
  BarChart3
} from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import api from '@/composables/useApi'

const dateRange = ref('30')
const loading = ref(false)

const analyticsStats = ref([
  { name: 'Total Views', value: '0', icon: Eye, iconBg: 'bg-primary/10', iconColor: 'text-primary' },
  { name: 'Total Likes', value: '0', icon: ThumbsUp, iconBg: 'bg-success/10', iconColor: 'text-success' },
  { name: 'Comments', value: '0', icon: MessageCircle, iconBg: 'bg-secondary/10', iconColor: 'text-secondary' },
  { name: 'Shares', value: '0', icon: Share2, iconBg: 'bg-warning/10', iconColor: 'text-warning' }
])

const loadAnalytics = async () => {
  loading.value = true
  try {
    const response = await api.get(`/analytics?days=${dateRange.value}`)
    const data = response.data
    
    analyticsStats.value = [
      { name: 'Total Views', value: (data.total_views || 0).toLocaleString(), icon: Eye, iconBg: 'bg-primary/10', iconColor: 'text-primary' },
      { name: 'Total Likes', value: (data.total_likes || 0).toLocaleString(), icon: ThumbsUp, iconBg: 'bg-success/10', iconColor: 'text-success' },
      { name: 'Comments', value: (data.total_comments || 0).toLocaleString(), icon: MessageCircle, iconBg: 'bg-secondary/10', iconColor: 'text-secondary' },
      { name: 'Shares', value: (data.total_shares || 0).toLocaleString(), icon: Share2, iconBg: 'bg-warning/10', iconColor: 'text-warning' }
    ]
  } catch (err) {
    console.error('Failed to load analytics:', err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAnalytics()
})
</script>
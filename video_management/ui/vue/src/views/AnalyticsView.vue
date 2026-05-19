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
          
          <Badge
            v-if="stat.change"
            :variant="stat.change > 0 ? 'success' : 'error'"
          >
            {{ stat.change > 0 ? '+' : '' }}{{ stat.change }}%
          </Badge>
        </div>
        
        <p class="text-2xl font-bold text-text-primary mb-1">{{ stat.value }}</p>
        <p class="text-sm text-text-secondary">{{ stat.name }}</p>
      </Card>
    </div>
    
    <!-- Charts -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card class="p-6">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Views Over Time</h2>
        <!-- Placeholder for chart -->
        <div class="h-64 bg-surface-elevated rounded-lg flex items-center justify-center">
          <TrendingUp class="w-12 h-12 text-text-muted" />
        </div>
      </Card>
      
      <Card class="p-6">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Platform Performance</h2>
        <!-- Placeholder for chart -->
        <div class="h-64 bg-surface-elevated rounded-lg flex items-center justify-center">
          <BarChart3 class="w-12 h-12 text-text-muted" />
        </div>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  Eye,
  ThumbsUp,
  MessageCircle,
  Share2,
  TrendingUp,
  BarChart3
} from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'

const dateRange = ref('30')

const analyticsStats = ref([
  { name: 'Total Views', value: '12.5K', change: 23, icon: Eye, iconBg: 'bg-primary/10', iconColor: 'text-primary' },
  { name: 'Total Likes', value: '892', change: 15, icon: ThumbsUp, iconBg: 'bg-success/10', iconColor: 'text-success' },
  { name: 'Comments', value: '156', change: -5, icon: MessageCircle, iconBg: 'bg-secondary/10', iconColor: 'text-secondary' },
  { name: 'Shares', value: '89', change: 42, icon: Share2, iconBg: 'bg-warning/10', iconColor: 'text-warning' }
])
</script>
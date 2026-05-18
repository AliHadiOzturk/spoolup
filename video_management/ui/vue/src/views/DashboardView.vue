<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-text-primary">Dashboard</h1>
        <p class="text-text-secondary mt-1">Overview of your video management system</p>
      </div>
      
      <Button variant="primary" @click="syncFromPrinter">
        <RefreshCw class="w-4 h-4" />
        <span>Sync from Printer</span>
      </Button>
    </div>
    
    <!-- Stats grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card
        v-for="stat in stats"
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
            :variant="stat.change > 0 ? 'success' : 'default'"
          >
            {{ stat.change > 0 ? '+' : '' }}{{ stat.change }}%
          </Badge>
        </div>
        
        <p class="text-2xl font-bold text-text-primary mb-1">{{ stat.value }}</p>
        <p class="text-sm text-text-secondary">{{ stat.name }}</p>
      </Card>
    </div>
    
    <!-- Main content grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Recent activity -->
      <Card class="lg:col-span-2 p-6">
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-lg font-semibold text-text-primary">Recent Activity</h2>
          <Button variant="ghost" size="sm">View All</Button>
        </div>
        
        <div class="space-y-4">
          <div
            v-for="(activity, index) in recentActivity"
            :key="index"
            class="flex items-start gap-4 p-3 rounded-lg hover:bg-surface-elevated transition-colors"
          >
            <div
              :class="[
                'w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0',
                activity.iconBg
              ]"
            >
              <component :is="activity.icon" :class="['w-5 h-5', activity.iconColor]" />
            </div>
            
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium text-text-primary">{{ activity.title }}</p>
              <p class="text-sm text-text-secondary mt-0.5">{{ activity.description }}</p>
            </div>
            
            <span class="text-xs text-text-muted whitespace-nowrap">{{ activity.time }}</span>
          </div>
        </div>
      </Card>
      
      <!-- Platform status -->
      <Card class="p-6">
        <h2 class="text-lg font-semibold text-text-primary mb-6">Platform Status</h2>
        
        <div class="space-y-4">
          <div
            v-for="platform in platforms"
            :key="platform.name"
            class="flex items-center justify-between p-3 rounded-lg bg-surface-elevated"
          >
            <div class="flex items-center gap-3">
              <div
                :class="[
                  'w-10 h-10 rounded-lg flex items-center justify-center',
                  platform.bgColor
                ]"
              >
                <component :is="platform.icon" class="w-5 h-5 text-white" />
              </div>
              
              <div>
                <p class="font-medium text-text-primary">{{ platform.name }}</p>
                <p class="text-sm text-text-secondary">{{ platform.status }}</p>
              </div>
            </div>
            
            <div
              :class="[
                'w-2.5 h-2.5 rounded-full',
                platform.connected ? 'bg-success' : 'bg-error'
              ]"
            />
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Video,
  Upload,
  CheckCircle,
  Eye,
  RefreshCw,
  Youtube,
  Music2,
  Printer,
  Film,
  Clock,
  AlertTriangle
} from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'
import api from '@/composables/useApi'

const stats = ref([
  { name: 'Total Videos', value: '—', icon: Video, iconBg: 'bg-primary/10', iconColor: 'text-primary' },
  { name: 'Pending Uploads', value: '—', icon: Upload, iconBg: 'bg-warning/10', iconColor: 'text-warning' },
  { name: 'Published', value: '—', icon: CheckCircle, iconBg: 'bg-success/10', iconColor: 'text-success' },
  { name: 'Total Views', value: '—', icon: Eye, iconBg: 'bg-secondary/10', iconColor: 'text-secondary' }
])

const platforms = ref([
  { name: 'YouTube', icon: Youtube, bgColor: 'bg-red-600', status: 'Connected', connected: true },
  { name: 'TikTok', icon: Music2, bgColor: 'bg-black', status: 'Connected', connected: true },
  { name: 'Printer', icon: Printer, bgColor: 'bg-primary', status: 'Online', connected: true }
])

const recentActivity = ref([
  { title: 'Video processed', description: 'timelapse_001.mp4 ready for upload', time: '2m ago', icon: Film, iconBg: 'bg-primary/10', iconColor: 'text-primary' },
  { title: 'Upload completed', description: 'Video uploaded to YouTube', time: '15m ago', icon: CheckCircle, iconBg: 'bg-success/10', iconColor: 'text-success' },
  { title: 'Sync completed', description: '3 new videos from printer', time: '1h ago', icon: RefreshCw, iconBg: 'bg-secondary/10', iconColor: 'text-secondary' },
  { title: 'Upload failed', description: 'TikTok upload failed - retrying', time: '2h ago', icon: AlertTriangle, iconBg: 'bg-error/10', iconColor: 'text-error' }
])

const syncFromPrinter = async () => {
  // Implementation
}

onMounted(async () => {
  try {
    const response = await api.get('/stats/dashboard')
    const data = response.data
    
    stats.value[0].value = data.total_videos?.toString() || '0'
    stats.value[1].value = data.pending_uploads?.toString() || '0'
    stats.value[2].value = data.published?.toString() || '0'
    stats.value[3].value = data.total_views?.toLocaleString() || '0'
  } catch (err) {
    console.error('Failed to load dashboard stats:', err)
  }
})
</script>
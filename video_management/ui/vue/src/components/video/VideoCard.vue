<template>
  <Card hoverable class="group">
    <div class="relative aspect-video bg-black rounded-t-xl overflow-hidden">
      <!-- Thumbnail -->
      <img
        v-if="video.thumbnail_path"
        :src="video.thumbnail_path"
        :alt="video.filename"
        class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
        loading="lazy"
      />
      <!-- Fallback -->
      <div
        v-else
        class="w-full h-full flex items-center justify-center bg-surface-elevated"
      >
        <Film class="w-12 h-12 text-text-muted" />
      </div>
      
      <!-- Overlay -->
      <div class="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
      
      <!-- Play button -->
      <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        <div class="w-12 h-12 rounded-full bg-primary/90 flex items-center justify-center backdrop-blur-sm">
          <Play class="w-5 h-5 text-white ml-0.5" />
        </div>
      </div>
      
      <!-- Duration badge -->
      <div class="absolute bottom-2 right-2 px-2 py-0.5 bg-black/70 rounded text-xs font-medium text-white backdrop-blur-sm">
        {{ formatDuration(video.duration_seconds) }}
      </div>
      
      <!-- Checkbox for bulk selection -->
      <div
        v-if="selectable"
        class="absolute top-2 left-2"
      >
        <input
          type="checkbox"
          :checked="selected"
          class="w-5 h-5 rounded border-border bg-surface/80 text-primary focus:ring-primary"
          @click.stop="$emit('toggle-select', video.id)"
        />
      </div>
    </div>
    
    <!-- Info -->
    <div class="p-4">
      <h3 class="font-medium text-text-primary truncate mb-1" :title="video.title || video.filename">
        {{ video.title || video.filename }}
      </h3>
      
      <div class="flex items-center gap-2 text-sm text-text-secondary mb-3">
        <span>{{ formatFileSize(video.size_bytes) }}</span>
        <span class="w-1 h-1 rounded-full bg-text-muted" />
        <span>{{ formatDate(video.created_at) }}</span>
      </div>
      
      <div class="flex items-center justify-between">
        <Badge
          :variant="video.metadata_status === 'complete' ? 'success' : 'warning'"
          :dot="true"
        >
          {{ video.metadata_status === 'complete' ? 'Complete' : 'Pending' }}
        </Badge>
        
        <div class="flex items-center gap-1">
          <RouterLink
            :to="`/videos/${video.id}`"
            class="p-1.5 rounded-lg text-text-muted hover:text-primary hover:bg-primary/10 transition-colors"
          >
            <Eye class="w-4 h-4" />
          </RouterLink>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { Film, Play, Eye } from 'lucide-vue-next'
import Card from '../ui/Card.vue'
import Badge from '../ui/Badge.vue'
import type { Video } from '@/stores/videos'

interface Props {
  video: Video
  selectable?: boolean
  selected?: boolean
}

withDefaults(defineProps<Props>(), {
  selectable: false,
  selected: false
})

defineEmits<{
  'toggle-select': [id: number]
}>()

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function formatFileSize(bytes: number): string {
  const sizes = ['B', 'KB', 'MB', 'GB']
  if (bytes === 0) return '0 B'
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric'
  })
}
</script>
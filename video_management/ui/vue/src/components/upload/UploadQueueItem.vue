<template>
  <Card class="p-4">
    <div class="flex items-center gap-4">
      <!-- Platform icon -->
      <div
        :class="[
          'w-10 h-10 rounded-lg flex items-center justify-center',
          platformColors[upload.platform] || platformColors.default
        ]"
      >
        <Youtube v-if="upload.platform === 'youtube'" class="w-5 h-5 text-white" />
        <Music2 v-else-if="upload.platform === 'tiktok'" class="w-5 h-5 text-white" />
        <UploadIcon v-else class="w-5 h-5 text-white" />
      </div>
      
      <!-- Info -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center justify-between mb-1">
          <h4 class="font-medium text-text-primary truncate">
            {{ upload.title || 'Untitled Upload' }}
          </h4>
          
          <Badge
            :variant="statusVariant"
            :dot="true"
          >
            {{ upload.status }}
          </Badge>
        </div>
        
        <ProgressBar
          v-if="showProgress"
          :value="upload.upload_progress || 0"
          label="Upload progress"
          variant="primary"
        />
        
        <p v-else-if="upload.error_message" class="text-sm text-error">
          {{ upload.error_message }}
        </p>
        
        <p v-else-if="upload.completed_at" class="text-sm text-text-secondary">
          Completed {{ formatDate(upload.completed_at) }}
        </p>
      </div>
      
      <!-- Actions -->
      <div class="flex items-center gap-2">
        <Button
          v-if="upload.status === 'failed'"
          variant="secondary"
          size="sm"
          @click="$emit('retry', upload.id)"
        >
          <RefreshCw class="w-4 h-4" />
        </Button>
        
        <Button
          v-if="canCancel"
          variant="ghost"
          size="sm"
          @click="$emit('cancel', upload.id)"
        >
          <X class="w-4 h-4" />
        </Button>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Youtube, Music2, Upload as UploadIcon, RefreshCw, X } from 'lucide-vue-next'
import Card from '../ui/Card.vue'
import Button from '../ui/Button.vue'
import Badge from '../ui/Badge.vue'
import ProgressBar from '../ui/ProgressBar.vue'
import type { Upload } from '@/stores/uploads'

interface Props {
  upload: Upload
}

const props = defineProps<Props>()

defineEmits<{
  retry: [id: number]
  cancel: [id: number]
}>()

const platformColors: Record<string, string> = {
  youtube: 'bg-red-600',
  tiktok: 'bg-black',
  default: 'bg-primary'
}

const statusVariant = computed(() => {
  switch (props.upload.status) {
    case 'completed': return 'success'
    case 'failed': return 'error'
    case 'uploading': return 'primary'
    case 'processing': return 'warning'
    default: return 'default'
  }
})

const showProgress = computed(() => {
  return props.upload.status === 'uploading' || props.upload.status === 'processing'
})

const canCancel = computed(() => {
  return props.upload.status === 'uploading' || props.upload.status === 'queued'
})

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>
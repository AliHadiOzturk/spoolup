<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-text-primary">Upload Queue</h1>
        <p class="text-text-secondary mt-1">Manage your video uploads</p>
      </div>
      
      <Button variant="primary" @click="refreshUploads">
        <RefreshCw class="w-4 h-4" />
        <span>Refresh</span>
      </Button>
    </div>
    
    <!-- Filter tabs -->
    <div class="flex gap-2">
      <button
        v-for="filter in filters"
        :key="filter.id"
        :class="[
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          activeFilter === filter.id
            ? 'bg-primary text-white'
            : 'bg-surface-elevated text-text-secondary hover:text-text-primary'
        ]"
        @click="activeFilter = filter.id"
      >
        {{ filter.name }}
        <span
          v-if="filter.count"
          :class="[
            'ml-2 px-2 py-0.5 rounded-full text-xs',
            activeFilter === filter.id
              ? 'bg-white/20'
              : 'bg-surface text-text-muted'
          ]"
        >
          {{ filter.count }}
        </span>
      </button>
    </div>
    
    <!-- Upload list -->
    <div v-if="!uploadStore.loading" class="space-y-3">
      <UploadQueueItem
        v-for="upload in filteredUploads"
        :key="upload.id"
        :upload="upload"
        @retry="retryUpload"
        @cancel="cancelUpload"
      />
      
      <!-- Empty state -->
      <Card
        v-if="filteredUploads.length === 0"
        class="p-12 text-center"
      >
        <Upload class="w-16 h-16 text-text-muted mx-auto mb-4" />
        <h3 class="text-lg font-medium text-text-primary mb-2">No uploads</h3>
        <p class="text-text-secondary">{{ emptyMessage }}</p>
      </Card>
    </div>
    
    <!-- Loading state -->
    <div v-else class="space-y-3">
      <Skeleton
        v-for="i in 4"
        :key="i"
        height="h-20"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RefreshCw, Upload } from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import UploadQueueItem from '@/components/upload/UploadQueueItem.vue'
import { useUploadStore } from '@/stores/uploads'

const uploadStore = useUploadStore()
const activeFilter = ref('all')

const filters = computed(() => [
  { id: 'all', name: 'All', count: uploadStore.uploads.length },
  { id: 'pending', name: 'Pending', count: uploadStore.uploads.filter(u => ['queued', 'pending'].includes(u.status)).length },
  { id: 'active', name: 'Active', count: uploadStore.uploads.filter(u => ['uploading', 'processing'].includes(u.status)).length },
  { id: 'completed', name: 'Completed', count: uploadStore.uploads.filter(u => u.status === 'completed').length },
  { id: 'failed', name: 'Failed', count: uploadStore.uploads.filter(u => u.status === 'failed').length }
])

const filteredUploads = computed(() => {
  if (activeFilter.value === 'all') return uploadStore.uploads
  if (activeFilter.value === 'pending') return uploadStore.uploads.filter(u => ['queued', 'pending'].includes(u.status))
  if (activeFilter.value === 'active') return uploadStore.uploads.filter(u => ['uploading', 'processing'].includes(u.status))
  if (activeFilter.value === 'completed') return uploadStore.uploads.filter(u => u.status === 'completed')
  if (activeFilter.value === 'failed') return uploadStore.uploads.filter(u => u.status === 'failed')
  return uploadStore.uploads
})

const emptyMessage = computed(() => {
  switch (activeFilter.value) {
    case 'pending': return 'No pending uploads'
    case 'active': return 'No active uploads'
    case 'completed': return 'No completed uploads'
    case 'failed': return 'No failed uploads'
    default: return 'No uploads yet. Process a video and upload it to get started.'
  }
})

const refreshUploads = () => {
  uploadStore.fetchUploads()
}

const retryUpload = async (id: number) => {
  await uploadStore.retryUpload(id)
  refreshUploads()
}

const cancelUpload = async (id: number) => {
  await uploadStore.cancelUpload(id)
  refreshUploads()
}

onMounted(() => {
  refreshUploads()
})
</script>
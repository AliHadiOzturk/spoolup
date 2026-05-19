<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-text-primary">Videos</h1>
        <p class="text-text-secondary mt-1">Manage your recorded timelapse videos</p>
      </div>
      
      <Button variant="primary" @click="syncFromPrinter">
        <RefreshCw class="w-4 h-4" />
        <span>Sync from Printer</span>
      </Button>
    </div>
    
    <!-- Filters and bulk actions -->
    <Card class="p-4">
      <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <input
            type="checkbox"
            :checked="allSelected"
            class="w-5 h-5 rounded border-border bg-surface text-primary focus:ring-primary"
            @change="toggleSelectAll"
          />
          
          <span class="text-sm text-text-secondary">
            {{ videoStore.selectedVideos.size }} selected
          </span>
          
          <span class="text-sm text-text-muted">{{ videoStore.videos.length }} total</span>
        </div>
        
        <div class="flex items-center gap-3 w-full sm:w-auto">
          <!-- Bulk actions -->
          <div
            v-if="videoStore.selectedVideos.size > 0"
            class="flex items-center gap-2"
          >
            <Button variant="primary" size="sm" @click="bulkProcess">
              <Wand2 class="w-4 h-4" />
              Process
            </Button>
            
            <Button variant="secondary" size="sm" @click="bulkUpload">
              <Upload class="w-4 h-4" />
              Upload
            </Button>
            
            <Button variant="ghost" size="sm" @click="bulkDelete">
              <Trash2 class="w-4 h-4" />
            </Button>
          </div>
          
          <!-- Sort -->
          <select
            v-model="sortBy"
            class="px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
            @change="loadVideos"
          >
            <option value="date">Date (Newest)</option>
            <option value="date_oldest">Date (Oldest)</option>
            <option value="name">Name (A-Z)</option>
            <option value="name_desc">Name (Z-A)</option>
            <option value="duration">Duration</option>
          </select>
        </div>
      </div>
    </Card>
    
    <!-- Video grid -->
    <div v-if="!videoStore.loading">
      <VideoGrid
        v-if="videoStore.videos.length > 0"
        :videos="videoStore.videos"
        :selectable="true"
        :selected-ids="videoStore.selectedVideos"
        @toggle-select="videoStore.toggleSelection"
      />
      
      <!-- Empty state -->
      <Card
        v-else
        class="p-12 text-center"
      >
        <Film class="w-16 h-16 text-text-muted mx-auto mb-4" />
        <h3 class="text-lg font-medium text-text-primary mb-2">No videos yet</h3>
        <p class="text-text-secondary mb-6 max-w-md mx-auto">
          Your video library is empty. Sync your printer to import timelapse videos and start managing your 3D print recordings.
        </p>
        
        <Button variant="primary" @click="syncFromPrinter">
          <RefreshCw class="w-4 h-4" />
          <span>Sync from Printer</span>
        </Button>
      </Card>
    </div>
    
    <!-- Loading state -->
    <div
      v-else
      class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
    >
      <Skeleton
        v-for="i in 8"
        :key="i"
        height="h-64"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RefreshCw, Wand2, Upload, Trash2, Film } from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import VideoGrid from '@/components/video/VideoGrid.vue'
import { useVideoStore } from '@/stores/videos'

const videoStore = useVideoStore()
const sortBy = ref('date')

const allSelected = computed(() => {
  return videoStore.videos.length > 0 && videoStore.selectedVideos.size === videoStore.videos.length
})

const loadVideos = () => {
  videoStore.fetchVideos(sortBy.value)
}

const toggleSelectAll = () => {
  if (allSelected.value) {
    videoStore.clearSelection()
  } else {
    videoStore.selectAll()
  }
}

const syncFromPrinter = async () => {
  // Implementation would sync from first printer
}

const bulkProcess = () => {
  // Implementation
}

const bulkUpload = () => {
  // Implementation
}

const bulkDelete = () => {
  // Implementation
}

onMounted(() => {
  loadVideos()
})
</script>
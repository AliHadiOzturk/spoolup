<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-text-primary">Audio Library</h1>
        <p class="text-text-secondary mt-1">Manage your audio tracks for video processing</p>
      </div>
      
      <Button variant="primary">
        <Upload class="w-4 h-4" />
        <span>Upload Track</span>
      </Button>
    </div>
    
    <!-- Audio tracks grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <Card
        v-for="track in audioTracks"
        :key="track.id"
        class="p-4 group"
      >
        <div class="flex items-center gap-4">
          <!-- Waveform visualization placeholder -->
          <div class="w-16 h-16 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
            <Music class="w-8 h-8 text-primary" />
          </div>
          
          <div class="flex-1 min-w-0">
            <h3 class="font-medium text-text-primary truncate">{{ track.name }}</h3>
            <p class="text-sm text-text-secondary">{{ formatDuration(track.duration) }}</p>
          </div>
          
          <button
            class="p-2 rounded-lg text-text-muted hover:text-primary hover:bg-primary/10 transition-colors opacity-0 group-hover:opacity-100"
            @click="playTrack(track)"
          >
            <Play class="w-5 h-5" />
          </button>
          
          <button
            class="p-2 rounded-lg text-text-muted hover:text-error hover:bg-error/10 transition-colors opacity-0 group-hover:opacity-100"
            @click="deleteTrack(track.id)"
          >
            <Trash2 class="w-5 h-5" />
          </button>
        </div>
      </Card>
    </div>
    
    <!-- Empty state -->
    <Card
      v-if="audioTracks.length === 0"
      class="p-12 text-center"
    >
      <Music class="w-16 h-16 text-text-muted mx-auto mb-4" />
      <h3 class="text-lg font-medium text-text-primary mb-2">No audio tracks</h3>
      <p class="text-text-secondary mb-6">Upload audio tracks to use in your video processing</p>
      
      <Button variant="primary">
        <Upload class="w-4 h-4" />
        Upload Track
      </Button>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Upload, Music, Play, Trash2 } from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import api from '@/composables/useApi'

interface AudioTrack {
  id: number
  name: string
  duration?: number
  file_path: string
}

const audioTracks = ref<AudioTrack[]>([])

const playTrack = (track: AudioTrack) => {
  // Implementation
}

const deleteTrack = async (id: number) => {
  // Implementation
}

function formatDuration(seconds?: number): string {
  if (!seconds) return 'Unknown duration'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

onMounted(async () => {
  try {
    const response = await api.get('/audio-tracks')
    audioTracks.value = response.data
  } catch (err) {
    console.error('Failed to load audio tracks:', err)
  }
})
</script>
<template>
  <div v-if="video" class="space-y-6">
    <!-- Back button and title -->
    <div class="flex items-center gap-4">
      <RouterLink
        to="/videos"
        class="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface-elevated transition-colors"
      >
        <ArrowLeft class="w-5 h-5" />
      </RouterLink>
      
      <div>
        <h1 class="text-2xl font-bold text-text-primary truncate">
          {{ video.title || video.filename }}
        </h1>
        <p class="text-text-secondary">{{ formatDate(video.created_at) }}</p>
      </div>
    </div>
    
    <!-- Video player and info -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Video player -->
      <div class="lg:col-span-2 space-y-4">
        <VideoPlayer
          :src="video.original_path"
          :controls="true"
        />
        
        <!-- Tabs -->
        <Card class="overflow-hidden">
          <div class="border-b border-border">
            <div class="flex">
              <button
                v-for="tab in tabs"
                :key="tab.id"
                :class="[
                  'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                  activeTab === tab.id
                    ? 'border-primary text-primary'
                    : 'border-transparent text-text-secondary hover:text-text-primary'
                ]"
                @click="activeTab = tab.id"
              >
                {{ tab.name }}
              </button>
            </div>
          </div>
          
          <div class="p-6">
            <!-- Metadata tab -->
            <div v-if="activeTab === 'metadata'" class="space-y-4">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input
                  v-model="form.title"
                  label="Title"
                  placeholder="Enter video title"
                />
                
                <Input
                  v-model="form.category"
                  label="Category"
                  placeholder="e.g., 3D Printing"
                />
              </div>
              
              <Input
                v-model="form.description"
                label="Description"
                placeholder="Enter video description"
                multiline
                :rows="4"
              />
              
              <div class="flex justify-end gap-3">
                <Button variant="secondary" @click="resetForm">Reset</Button>
                <Button variant="primary" @click="saveMetadata">Save Changes</Button>
              </div>
            </div>
            
            <!-- Processing tab -->
            <div v-else-if="activeTab === 'processing'" class="space-y-4">
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div class="p-4 bg-surface-elevated rounded-lg">
                  <p class="text-sm text-text-secondary mb-1">Resolution</p>
                  <p class="text-lg font-semibold text-text-primary">{{ video.width }}x{{ video.height }}</p>
                </div>
                
                <div class="p-4 bg-surface-elevated rounded-lg">
                  <p class="text-sm text-text-secondary mb-1">Duration</p>
                  <p class="text-lg font-semibold text-text-primary">{{ formatDuration(video.duration_seconds) }}</p>
                </div>
                
                <div class="p-4 bg-surface-elevated rounded-lg">
                  <p class="text-sm text-text-secondary mb-1">FPS</p>
                  <p class="text-lg font-semibold text-text-primary">{{ video.fps }}</p>
                </div>
                
                <div class="p-4 bg-surface-elevated rounded-lg">
                  <p class="text-sm text-text-secondary mb-1">Size</p>
                  <p class="text-lg font-semibold text-text-primary">{{ formatFileSize(video.size_bytes) }}</p>
                </div>
              </div>
              
              <Button variant="primary" class="w-full">
                <Wand2 class="w-4 h-4" />
                Process Video
              </Button>
            </div>
            
            <!-- Uploads tab -->
            <div v-else-if="activeTab === 'uploads'">
              <div v-if="uploads.length > 0" class="space-y-3">
                <UploadQueueItem
                  v-for="upload in uploads"
                  :key="upload.id"
                  :upload="upload"
                />
              </div>
              
              <div v-else class="text-center py-8">
                <Upload class="w-12 h-12 text-text-muted mx-auto mb-3" />
                <p class="text-text-secondary">No uploads yet</p>
              </div>
            </div>
            
            <!-- Analytics tab -->
            <div v-else-if="activeTab === 'analytics'">
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                <Card class="p-4 text-center">
                  <Eye class="w-5 h-5 text-primary mx-auto mb-2" />
                  <p class="text-2xl font-bold text-text-primary">1.2K</p>
                  <p class="text-sm text-text-secondary">Views</p>
                </Card>
                
                <Card class="p-4 text-center">
                  <ThumbsUp class="w-5 h-5 text-success mx-auto mb-2" />
                  <p class="text-2xl font-bold text-text-primary">89</p>
                  <p class="text-sm text-text-secondary">Likes</p>
                </Card>
                
                <Card class="p-4 text-center">
                  <MessageCircle class="w-5 h-5 text-secondary mx-auto mb-2" />
                  <p class="text-2xl font-bold text-text-primary">12</p>
                  <p class="text-sm text-text-secondary">Comments</p>
                </Card>
                
                <Card class="p-4 text-center">
                  <Share2 class="w-5 h-5 text-warning mx-auto mb-2" />
                  <p class="text-2xl font-bold text-text-primary">5</p>
                  <p class="text-sm text-text-secondary">Shares</p>
                </Card>
              </div>
            </div>
          </div>
        </Card>
      </div>
      
      <!-- Sidebar -->
      <div class="space-y-4">
        <!-- Quick actions -->
        <Card class="p-4">
          <h3 class="font-medium text-text-primary mb-3">Quick Actions</h3>
          
          <div class="space-y-2">
            <Button variant="primary" class="w-full">
              <Upload class="w-4 h-4" />
              Upload to YouTube
            </Button>
            
            <Button variant="secondary" class="w-full">
              <Music2 class="w-4 h-4" />
              Upload to TikTok
            </Button>
            
            <Button variant="ghost" class="w-full">
              <Download class="w-4 h-4" />
              Download
            </Button>
          </div>
        </Card>
        
        <!-- Info card -->
        <Card class="p-4">
          <h3 class="font-medium text-text-primary mb-3">Video Info</h3>
          
          <div class="space-y-2 text-sm">
            <div class="flex justify-between">
              <span class="text-text-secondary">Status</span>
              <Badge
                :variant="video.metadata_status === 'complete' ? 'success' : 'warning'"
                :dot="true"
              >
                {{ video.metadata_status }}
              </Badge>
            </div>
            
            <div class="flex justify-between">
              <span class="text-text-secondary">Created</span>
              <span class="text-text-primary">{{ formatDate(video.created_at) }}</span>
            </div>
            
            <div class="flex justify-between">
              <span class="text-text-secondary">Modified</span>
              <span class="text-text-primary">{{ video.modified_at ? formatDate(video.modified_at) : 'Never' }}</span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  </div>
  
  <!-- Loading state -->
  <div v-else class="flex items-center justify-center h-64">
    <Loader2 class="w-8 h-8 text-primary animate-spin" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  ArrowLeft,
  Wand2,
  Upload,
  Download,
  Music2,
  Eye,
  ThumbsUp,
  MessageCircle,
  Share2,
  Loader2
} from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'
import Input from '@/components/ui/Input.vue'
import VideoPlayer from '@/components/video/VideoPlayer.vue'
import UploadQueueItem from '@/components/upload/UploadQueueItem.vue'
import { useVideoStore } from '@/stores/videos'
import type { Video } from '@/stores/videos'
import type { Upload } from '@/stores/uploads'

const route = useRoute()
const videoStore = useVideoStore()

const video = ref<Video | null>(null)
const uploads = ref<Upload[]>([])
const activeTab = ref('metadata')

const tabs = [
  { id: 'metadata', name: 'Metadata' },
  { id: 'processing', name: 'Processing' },
  { id: 'uploads', name: 'Uploads' },
  { id: 'analytics', name: 'Analytics' }
]

const form = ref({
  title: '',
  description: '',
  category: ''
})

const loadVideo = async () => {
  const id = parseInt(route.params.id as string)
  const data = await videoStore.fetchVideo(id)
  if (data) {
    video.value = data
    form.value = {
      title: data.title || '',
      description: data.description || '',
      category: data.category || ''
    }
  }
}

const saveMetadata = async () => {
  // Implementation
}

const resetForm = () => {
  if (video.value) {
    form.value = {
      title: video.value.title || '',
      description: video.value.description || '',
      category: video.value.category || ''
    }
  }
}

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
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  loadVideo()
})
</script>
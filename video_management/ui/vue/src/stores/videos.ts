import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

export interface Video {
  id: number
  filename: string
  title?: string
  description?: string
  size_bytes: number
  duration_seconds: number
  width: number
  height: number
  fps: number
  created_at: string
  modified_at?: string
  metadata_status: string
  thumbnail_path?: string
  printer_id: number
  printer_name?: string
}

export const useVideoStore = defineStore('videos', () => {
  const videos = ref<Video[]>([])
  const loading = ref(false)
  const selectedVideos = ref<Set<number>>(new Set())
  const currentVideo = ref<Video | null>(null)

  const fetchVideos = async (sortBy = 'date') => {
    loading.value = true
    try {
      const response = await api.get(`/videos?sort_by=${sortBy}`)
      videos.value = response.data
    } catch (err) {
      console.error('Failed to fetch videos:', err)
    } finally {
      loading.value = false
    }
  }

  const fetchVideo = async (id: number) => {
    try {
      const response = await api.get(`/videos/${id}`)
      currentVideo.value = response.data
      return response.data
    } catch (err) {
      console.error('Failed to fetch video:', err)
      return null
    }
  }

  const toggleSelection = (id: number) => {
    if (selectedVideos.value.has(id)) {
      selectedVideos.value.delete(id)
    } else {
      selectedVideos.value.add(id)
    }
  }

  const selectAll = () => {
    videos.value.forEach(v => selectedVideos.value.add(v.id))
  }

  const clearSelection = () => {
    selectedVideos.value.clear()
  }

  const syncFromPrinter = async (printerId: number) => {
    const response = await api.post(`/printers/${printerId}/sync`)
    return response.data
  }

  return {
    videos,
    loading,
    selectedVideos,
    currentVideo,
    fetchVideos,
    fetchVideo,
    toggleSelection,
    selectAll,
    clearSelection,
    syncFromPrinter
  }
})
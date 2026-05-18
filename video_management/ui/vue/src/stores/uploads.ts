import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

export interface Upload {
  id: number
  platform: string
  status: string
  title?: string
  upload_progress?: number
  scheduled_for?: string
  completed_at?: string
  error_message?: string
  processed_video_id: number
}

export const useUploadStore = defineStore('uploads', () => {
  const uploads = ref<Upload[]>([])
  const loading = ref(false)

  const fetchUploads = async () => {
    loading.value = true
    try {
      const response = await api.get('/uploads')
      uploads.value = response.data
    } catch (err) {
      console.error('Failed to fetch uploads:', err)
    } finally {
      loading.value = false
    }
  }

  const retryUpload = async (id: number) => {
    await api.post(`/uploads/${id}/retry`)
  }

  const cancelUpload = async (id: number) => {
    await api.post(`/uploads/${id}/cancel`)
  }

  return {
    uploads,
    loading,
    fetchUploads,
    retryUpload,
    cancelUpload
  }
})
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/composables/useApi'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loading = ref(false)
  const initialized = ref(false)

  const isAuthenticated = computed(() => !!user.value)

  const login = async (username: string, password: string) => {
    loading.value = true
    
    try {
      const formData = new URLSearchParams()
      formData.append('username', username)
      formData.append('password', password)
      
      const response = await api.post('/auth/token', formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        }
      })
      
      localStorage.setItem('access_token', response.data.access_token)
      await fetchUser()
      return true
    } catch (err: any) {
      throw new Error(err.response?.data?.detail || 'Login failed')
    } finally {
      loading.value = false
    }
  }

  const fetchUser = async () => {
    try {
      const response = await api.get('/auth/me')
      user.value = response.data
    } catch {
      user.value = null
      localStorage.removeItem('access_token')
    } finally {
      initialized.value = true
    }
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    user.value = null
  }

  return {
    user,
    loading,
    initialized,
    isAuthenticated,
    login,
    logout,
    fetchUser
  }
})
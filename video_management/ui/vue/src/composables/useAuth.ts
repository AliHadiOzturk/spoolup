import { ref, computed } from 'vue'
import api from './useApi'

export function useAuth() {
  const user = ref(null)
  const loading = ref(false)
  const error = ref('')

  const isAuthenticated = computed(() => !!localStorage.getItem('access_token'))

  const login = async (username: string, password: string) => {
    loading.value = true
    error.value = ''
    
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
      error.value = err.response?.data?.detail || 'Login failed'
      return false
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
    }
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    user.value = null
    window.location.href = '/login'
  }

  return {
    user,
    loading,
    error,
    isAuthenticated,
    login,
    logout,
    fetchUser
  }
}
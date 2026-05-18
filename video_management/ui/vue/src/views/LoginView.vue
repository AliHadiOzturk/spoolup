<template>
  <div class="min-h-screen flex items-center justify-center relative overflow-hidden">
    <!-- Animated background -->
    <div class="absolute inset-0 bg-background">
      <div class="absolute top-0 left-1/4 w-96 h-96 bg-primary/20 rounded-full blur-3xl animate-pulse-slow" />
      <div class="absolute bottom-0 right-1/4 w-96 h-96 bg-secondary/20 rounded-full blur-3xl animate-pulse-slow" style="animation-delay: 1.5s" />
    </div>
    
    <!-- Login card -->
    <div class="relative w-full max-w-md mx-4">
      <div class="bg-surface/80 backdrop-blur-xl border border-border rounded-2xl p-8 shadow-2xl">
        <!-- Logo -->
        <div class="text-center mb-8">
          <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-secondary flex items-center justify-center mx-auto mb-4 shadow-lg shadow-primary/25">
            <Play class="w-8 h-8 text-white" />
          </div>
          <h1 class="text-2xl font-bold text-text-primary mb-1">Video Management System</h1>
          <p class="text-text-secondary">Sign in to your account</p>
        </div>
        
        <!-- Form -->
        <form @submit.prevent="handleLogin" class="space-y-5">
          <div class="space-y-1">
            <label class="block text-sm font-medium text-text-secondary">Username</label>
            <div class="relative">
              <User class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted" />
              <input
                v-model="username"
                type="text"
                required
                class="w-full pl-10 pr-4 py-2.5 bg-surface-elevated border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/50 transition-all"
                placeholder="Enter your username"
                :disabled="loading"
              />
            </div>
          </div>
          
          <div class="space-y-1">
            <label class="block text-sm font-medium text-text-secondary">Password</label>
            <div class="relative">
              <Lock class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted" />
              <input
                v-model="password"
                type="password"
                required
                class="w-full pl-10 pr-4 py-2.5 bg-surface-elevated border border-border rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/50 transition-all"
                placeholder="Enter your password"
                :disabled="loading"
              />
            </div>
          </div>
          
          <!-- Error message -->
          <div
            v-if="error"
            class="p-3 bg-error/10 border border-error/20 rounded-lg text-sm text-error animate-shake"
          >
            {{ error }}
          </div>
          
          <button
            type="submit"
            :disabled="loading"
            class="w-full py-2.5 bg-primary text-white rounded-lg font-medium transition-all duration-200 hover:bg-primary-hover hover:shadow-lg hover:shadow-primary/25 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            <Loader2 v-if="loading" class="w-5 h-5 animate-spin" />
            <span>{{ loading ? 'Signing in...' : 'Sign In' }}</span>
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Play, User, Lock, Loader2 } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

const handleLogin = async () => {
  loading.value = true
  error.value = ''
  
  try {
    await authStore.login(username.value, password.value)
    router.push('/')
  } catch (err: any) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>
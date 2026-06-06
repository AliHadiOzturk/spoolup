<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div>
      <h1 class="text-2xl font-bold text-text-primary">Settings</h1>
      <p class="text-text-secondary mt-1">Configure your video management system</p>
    </div>
    
    <!-- Loading state -->
    <div v-if="loading" class="flex items-center justify-center h-64">
      <Loader2 class="w-8 h-8 text-primary animate-spin" />
    </div>
    
    <!-- Settings sections -->
    <div v-else class="space-y-6">
      <!-- Platform Settings -->
      <Card class="p-6">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Platform Settings</h2>
        
        <div class="space-y-4">
          <!-- YouTube -->
          <div class="p-4 bg-surface-elevated rounded-lg">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-red-600 flex items-center justify-center">
                  <Youtube class="w-5 h-5 text-white" />
                </div>
                
                <div>
                  <p class="font-medium text-text-primary">YouTube</p>
                  <p class="text-sm text-text-secondary">
                    {{ settings.youtube_connected 
                      ? (settings.youtube_email || 'Connected') 
                      : 'Not connected' 
                    }}
                  </p>
                </div>
              </div>
              
              <div class="flex items-center gap-2">
                <Badge :variant="settings.youtube_connected ? 'success' : 'warning'">
                  {{ settings.youtube_connected ? 'Connected' : 'Disconnected' }}
                </Badge>
              </div>
            </div>
            
            <p v-if="!settings.youtube_connected" class="text-sm text-text-secondary mt-2">
              Connect your YouTube account to upload videos directly to your channel.
            </p>
          </div>
          
          <!-- TikTok -->
          <div class="p-4 bg-surface-elevated rounded-lg">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-black flex items-center justify-center">
                  <Music2 class="w-5 h-5 text-white" />
                </div>
                
                <div>
                  <p class="font-medium text-text-primary">TikTok</p>
                  <p class="text-sm text-text-secondary">
                    {{ settings.tiktok_connected ? 'Connected' : 'Not connected' }}
                  </p>
                </div>
              </div>
              
              <div class="flex items-center gap-2">
                <Badge :variant="settings.tiktok_connected ? 'success' : 'warning'">
                  {{ settings.tiktok_connected ? 'Connected' : 'Disconnected' }}
                </Badge>
              </div>
            </div>
            
            <div v-if="settings.tiktok_connected" class="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">Privacy Level</label>
                <select
                  v-model="settings.tiktok_default_privacy"
                  class="w-full px-3 py-2 bg-surface border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
                  disabled
                >
                  <option value="private">Private (Required for unaudited apps)</option>
                </select>
                <p class="text-xs text-text-secondary mt-1">TikTok apps in sandbox mode can only upload private videos.</p>
              </div>
            </div>
            
            <div v-else class="mt-4 space-y-3">
              <p class="text-sm text-text-secondary">
                Connect your TikTok account to upload videos. Note: Only private uploads are allowed for unaudited apps.
              </p>
              <Button
                variant="primary"
                size="sm"
                :loading="connectingTiktok"
                @click="connectTikTok"
              >
                <Link2 class="w-4 h-4" />
                Connect TikTok Account
              </Button>
            </div>
          </div>
          
          <!-- Moonraker -->
          <div class="p-4 bg-surface-elevated rounded-lg">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Printer class="w-5 h-5 text-primary" />
                </div>
                
                <div>
                  <p class="font-medium text-text-primary">Moonraker</p>
                  <p class="text-sm text-text-secondary">{{ settings.moonraker_url || 'Not configured' }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>
      
      <!-- Processing Defaults -->
      <Card class="p-6">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Processing Defaults</h2>
        
        
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Output Resolution</label>
            <select
              v-model="settings.processing_defaults.resolution"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="1080x1920">1080x1920 (Shorts)</option>
              <option value="1920x1080">1920x1080 (HD)</option>
              <option value="3840x2160">3840x2160 (4K)</option>
            </select>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Max Duration (seconds)</label>
            <input
              v-model.number="settings.processing_defaults.max_duration"
              type="number"
              min="1"
              max="300"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
            />
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Crop Mode</label>
            <select
              v-model="settings.processing_defaults.crop_mode"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="center">Center</option>
              <option value="left">Left</option>
              <option value="right">Right</option>
            </select>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Zoom Level</label>
            <select
              v-model="settings.processing_defaults.zoom_level"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="0">No Zoom</option>
              <option value="0.1">0.1x (Zoom Out)</option>
              <option value="0.5">0.5x (Zoom Out)</option>
              <option value="1">1.0x (Standard)</option>
              <option value="1.5">1.5x (Zoom In)</option>
              <option value="2">2.0x (Zoom In)</option>
            </select>
          </div>
        </div>
        
        <p class="text-sm text-text-secondary mt-4">
          <AlertTriangle class="w-4 h-4 inline mr-1" />
          Processing defaults are applied when creating new videos. Update your .env file to make these changes persist across restarts.
        </p>
      </Card>
      
      <!-- Feature Flags -->
      <Card class="p-6">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Features</h2>
        
        
        <div class="space-y-3">
          <div class="flex items-center justify-between p-3 bg-surface-elevated rounded-lg">
            <div class="flex items-center gap-3">
              <Upload class="w-5 h-5 text-text-secondary" />
              <div>
                <p class="font-medium text-text-primary">TikTok Upload</p>
                <p class="text-sm text-text-secondary">Enable uploading to TikTok</p>
              </div>
            </div>
            
            <div class="relative inline-block">
              <input
                v-model="settings.features.enable_tiktok_upload"
                type="checkbox"
                class="w-5 h-5 rounded border-border text-primary focus:ring-primary"
              />
            </div>
          </div>
          
          <div class="flex items-center justify-between p-3 bg-surface-elevated rounded-lg">
            <div class="flex items-center gap-3">
              <Wand2 class="w-5 h-5 text-text-secondary" />
              <div>
                <p class="font-medium text-text-primary">Post Processing</p>
                <p class="text-sm text-text-secondary">Enable video post-processing features</p>
              </div>
            </div>
            
            <div class="relative inline-block">
              <input
                v-model="settings.features.enable_post_processing"
                type="checkbox"
                class="w-5 h-5 rounded border-border text-primary focus:ring-primary"
              />
            </div>
          </div>
          
          <div class="flex items-center justify-between p-3 bg-surface-elevated rounded-lg">
            <div class="flex items-center gap-3">
              <Layers class="w-5 h-5 text-text-secondary" />
              <div>
                <p class="font-medium text-text-primary">Bulk Operations</p>
                <p class="text-sm text-text-secondary">Enable bulk video operations</p>
              </div>
            </div>
            
            <div class="relative inline-block">
              <input
                v-model="settings.features.enable_bulk_operations"
                type="checkbox"
                class="w-5 h-5 rounded border-border text-primary focus:ring-primary"
              />
            </div>
          </div>
        </div>
        
        <p class="text-sm text-text-secondary mt-4">
          <AlertTriangle class="w-4 h-4 inline mr-1" />
          Feature flags require updating the .env file to persist across restarts.
        </p>
      </Card>
      
      <!-- Upload Settings -->
      <Card class="p-6">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Upload Settings</h2>
        
        
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Max Concurrent Uploads</label>
            <input
              v-model.number="settings.upload_settings.max_concurrent_uploads"
              type="number"
              min="1"
              max="10"
              disabled
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary opacity-50"
            />
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Max Upload Retries</label>
            <input
              v-model.number="settings.upload_settings.max_upload_retries"
              type="number"
              min="0"
              max="10"
              disabled
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary opacity-50"
            />
          </div>
        </div>
        
        <p class="text-sm text-text-secondary mt-4">
          <AlertTriangle class="w-4 h-4 inline mr-1" />
          Upload settings require updating the .env file to persist across restarts.
        </p>
      </Card>
      
      <!-- Save button -->
      <div class="flex justify-end">
        <Button
          variant="primary"
          :loading="saving"
          @click="saveSettings"
        >
          <Save class="w-4 h-4" />
          Save Settings
        </Button>
      </div>
      
      <!-- Save status -->
      <div v-if="saveStatus" class="mt-4">
        <div
          :class="[
            'px-4 py-3 rounded-lg text-sm',
            saveStatus.type === 'success' ? 'bg-success/10 text-success' :
            saveStatus.type === 'error' ? 'bg-error/10 text-error' :
            'bg-primary/10 text-primary'
          ]"
        >
          {{ saveStatus.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Youtube,
  Music2,
  Save,
  Loader2,
  Printer,
  Upload,
  Wand2,
  Layers,
  AlertTriangle,
  Link2
} from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'
import api from '@/composables/useApi'

const loading = ref(true)
const saving = ref(false)
const saveStatus = ref<{ type: string; message: string } | null>(null)

const settings = ref<any>({
  youtube_connected: false,
  youtube_email: null,
  tiktok_connected: false,
  tiktok_default_privacy: 'private',
  processing_defaults: {
    resolution: '1080x1920',
    max_duration: 60,
    crop_mode: 'center',
    zoom_level: 0.1
  },
  moonraker_url: '',
  features: {
    enable_tiktok_upload: true,
    enable_post_processing: true,
    enable_bulk_operations: false
  },
  upload_settings: {
    max_concurrent_uploads: 1,
    max_upload_retries: 3
  }
})

const loadSettings = async () => {
  loading.value = true
  try {
    const response = await api.get('/settings')
    settings.value = { ...settings.value, ...response.data }
  } catch (err) {
    console.error('Failed to load settings:', err)
  } finally {
    loading.value = false
  }
}

const saveSettings = async () => {
  saving.value = true
  saveStatus.value = null
  
  try {
    const response = await api.put('/settings', {
      processing_defaults: settings.value.processing_defaults,
      tiktok_default_privacy: settings.value.tiktok_default_privacy
    })
    
    saveStatus.value = {
      type: 'success',
      message: response.data.message || 'Settings saved successfully!'
    }
    
    setTimeout(() => {
      saveStatus.value = null
    }, 5000)
  } catch (err: any) {
    saveStatus.value = {
      type: 'error',
      message: err.response?.data?.detail || 'Failed to save settings'
    }
  } finally {
    saving.value = false
  }
}

const connectingTiktok = ref(false)

const connectTikTok = async () => {
  connectingTiktok.value = true
  try {
    const response = await api.get('/tiktok/auth')
    if (response.data.auth_url) {
      // Open auth URL in a popup window
      const width = 600
      const height = 700
      const left = window.screenX + (window.outerWidth - width) / 2
      const top = window.screenY + (window.outerHeight - height) / 2
      const popup = window.open(
        response.data.auth_url,
        'tiktok-auth',
        `width=${width},height=${height},left=${left},top=${top}`
      )
      
      if (!popup) {
        // Popup blocked, redirect in same window
        window.location.href = response.data.auth_url
        return
      }
      
      // Poll for popup closure to refresh settings
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed)
          loadSettings()
        }
      }, 1000)
      
      // Also poll settings every few seconds while popup is open
      const refreshInterval = setInterval(() => {
        if (popup.closed) {
          clearInterval(refreshInterval)
        } else {
          loadSettings()
        }
      }, 5000)
    }
  } catch (err: any) {
    alert(err.response?.data?.detail || 'Failed to initiate TikTok connection')
  } finally {
    connectingTiktok.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>
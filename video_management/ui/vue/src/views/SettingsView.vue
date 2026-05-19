<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div>
      <h1 class="text-2xl font-bold text-text-primary">Settings</h1>
      <p class="text-text-secondary mt-1">Configure your video management system</p>
    </div>
    
    <!-- Settings sections -->
    <div class="space-y-6">
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
                  <p class="text-sm text-text-secondary">Connected as {{ settings.youtube_email || 'user@example.com' }}</p>
                </div>
              </div>
              
              <Button variant="secondary" size="sm">
                <Unlink class="w-4 h-4" />
                Disconnect
              </Button>
            </div>
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
                  <p class="text-sm text-text-secondary">Connected as {{ settings.tiktok_username || '@username' }}</p>
                </div>
              </div>
              
              <Button variant="secondary" size="sm">
                <Unlink class="w-4 h-4" />
                Disconnect
              </Button>
            </div>
            
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">Privacy Level</label>
                <select class="w-full px-3 py-2 bg-surface border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
                >
                  <option value="private">Private</option>
                  <option value="friends">Friends Only</option>
                  <option value="public">Public</option>
                </select>
              </div>
              
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">Allow Comments</label>
                <select class="w-full px-3 py-2 bg-surface border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
                >
                  <option value="all">All</option>
                  <option value="friends">Friends Only</option>
                  <option value="none">None</option>
                </select>
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
            <select class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="1080x1920">1080x1920 (Shorts)</option>
              <option value="1920x1080">1920x1080 (HD)</option>
              <option value="3840x2160">3840x2160 (4K)</option>
            </select>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Max Duration (seconds)</label>
            <input
              type="number"
              value="60"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
            />
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Crop Mode</label>
            <select class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="center">Center</option>
              <option value="top">Top</option>
              <option value="bottom">Bottom</option>
            </select>
          </div>
        </div>
      </Card>
      
      <!-- Save button -->
      <div class="flex justify-end">
        <Button variant="primary">
          <Save class="w-4 h-4" />
          Save Settings
        </Button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Youtube, Music2, Unlink, Save } from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'

const settings = ref({
  youtube_email: '',
  tiktok_username: ''
})
</script>
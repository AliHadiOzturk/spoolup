<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-text-primary">Printers</h1>
        <p class="text-text-secondary mt-1">Manage your 3D printers</p>
      </div>
      
      <Button variant="primary">
        <Plus class="w-4 h-4" />
        <span>Add Printer</span>
      </Button>
    </div>
    
    <!-- Printer grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <Card
        v-for="printer in printers"
        :key="printer.id"
        class="p-6"
      >
        <div class="flex items-start justify-between mb-4">
          <div class="flex items-center gap-3">
            <div class="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
              <Printer class="w-6 h-6 text-primary" />
            </div>
            
            <div>
              <h3 class="font-semibold text-text-primary">{{ printer.name }}</h3>
              <p class="text-sm text-text-secondary">{{ printer.moonraker_url }}</p>
            </div>
          </div>
          
          <div
            :class="[
              'w-3 h-3 rounded-full',
              printer.is_active ? 'bg-success' : 'bg-error'
            ]"
            :title="printer.is_active ? 'Online' : 'Offline'"
          />
        </div>
        
        <div class="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            class="flex-1"
            @click="syncPrinter(printer.id)"
          >
            <RefreshCw class="w-4 h-4" />
            Sync
          </Button>
          
          <Button
            variant="ghost"
            size="sm"
          >
            <Settings class="w-4 h-4" />
          </Button>
        </div>
      </Card>
    </div>
    
    <!-- Empty state -->
    <Card
      v-if="printers.length === 0"
      class="p-12 text-center"
    >
      <Printer class="w-16 h-16 text-text-muted mx-auto mb-4" />
      <h3 class="text-lg font-medium text-text-primary mb-2">No printers configured</h3>
      <p class="text-text-secondary mb-6">Add a printer to start syncing videos</p>
      
      <Button variant="primary">
        <Plus class="w-4 h-4" />
        Add Printer
      </Button>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Printer, RefreshCw, Settings } from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import api from '@/composables/useApi'

interface Printer {
  id: number
  name: string
  moonraker_url: string
  is_active: boolean
}

const printers = ref<Printer[]>([])

const syncPrinter = async (id: number) => {
  await api.post(`/printers/${id}/sync`)
}

onMounted(async () => {
  try {
    const response = await api.get('/printers')
    printers.value = response.data
  } catch (err) {
    console.error('Failed to load printers:', err)
  }
})
</script>
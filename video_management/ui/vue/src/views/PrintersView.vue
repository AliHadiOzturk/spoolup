<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-text-primary">Printers</h1>
        <p class="text-text-secondary mt-1">Manage your 3D printers</p>
      </div>
      
      <Button variant="primary" @click="showAddModal = true">
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
            :loading="syncingId === printer.id"
            @click="syncPrinter(printer.id)"
          >
            <RefreshCw class="w-4 h-4" />
            Sync
          </Button>
          
          <Button
            variant="ghost"
            size="sm"
            @click="openSettings(printer)"
          >
            <Settings class="w-4 h-4" />
          </Button>

          <Button
            variant="ghost"
            size="sm"
            :loading="deletingId === printer.id"
            @click="deletePrinter(printer)"
          >
            <Trash2 class="w-4 h-4 text-error" />
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
      
      <Button variant="primary" @click="showAddModal = true">
        <Plus class="w-4 h-4" />
        Add Printer
      </Button>
    </Card>
    
    <!-- Add Printer Modal -->
    <Modal v-model="showAddModal" title="Add Printer">
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-text-secondary mb-1">Printer Name</label>
          <Input v-model="newPrinter.name" placeholder="e.g. K1 Max" />
        </div>
        
        <div>
          <label class="block text-sm font-medium text-text-secondary mb-1">Moonraker URL</label>
          <Input v-model="newPrinter.moonraker_url" placeholder="http://192.168.1.100:7125" />
        </div>
      </div>
      
      <template #footer>
        <Button variant="secondary" @click="showAddModal = false">
          Cancel
        </Button>
        <Button variant="primary" :loading="adding" @click="addPrinter">
          Add Printer
        </Button>
      </template>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Printer, RefreshCw, Settings, Trash2 } from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

interface Printer {
  id: number
  name: string
  moonraker_url: string
  is_active: boolean
}

const printers = ref<Printer[]>([])
const showAddModal = ref(false)
const syncingId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const adding = ref(false)
const newPrinter = ref({ name: '', moonraker_url: '' })
const toast = useToast()

const loadPrinters = async () => {
  try {
    const response = await api.get('/printers')
    printers.value = response.data
  } catch (err) {
    toast.error('Failed to load printers')
    console.error('Failed to load printers:', err)
  }
}

const syncPrinter = async (id: number) => {
  syncingId.value = id
  try {
    await api.post(`/printers/${id}/sync`)
    toast.success('Sync started successfully')
  } catch (err) {
    toast.error('Failed to sync printer')
    console.error('Failed to sync printer:', err)
  } finally {
    syncingId.value = null
  }
}

const addPrinter = async () => {
  if (!newPrinter.value.name || !newPrinter.value.moonraker_url) {
    toast.error('Please fill in all fields')
    return
  }
  
  adding.value = true
  try {
    await api.post('/printers', newPrinter.value)
    toast.success('Printer added successfully')
    showAddModal.value = false
    newPrinter.value = { name: '', moonraker_url: '' }
    await loadPrinters()
  } catch (err) {
    toast.error('Failed to add printer')
    console.error('Failed to add printer:', err)
  } finally {
    adding.value = false
  }
}

const deletePrinter = async (printer: Printer) => {
  if (!confirm(`Are you sure you want to delete "${printer.name}"?`)) return

  deletingId.value = printer.id
  try {
    await api.delete(`/printers/${printer.id}`)
    toast.success('Printer deleted successfully')
    await loadPrinters()
  } catch (err) {
    toast.error('Failed to delete printer')
    console.error('Failed to delete printer:', err)
  } finally {
    deletingId.value = null
  }
}

const openSettings = (printer: Printer) => {
  toast.info(`Settings for ${printer.name} - coming soon`)
}

onMounted(loadPrinters)
</script>
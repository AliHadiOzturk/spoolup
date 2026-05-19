<template>
  <Teleport to="body">
    <div class="fixed top-20 right-6 z-50 flex flex-col gap-3 pointer-events-none">
      <TransitionGroup
        enter-active-class="transition-all duration-300 ease-out"
        enter-from-class="opacity-0 translate-x-6 scale-95"
        leave-active-class="transition-all duration-200 ease-in"
        leave-to-class="opacity-0 translate-x-6 scale-95"
      >
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="[
            'pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg border min-w-[300px] max-w-[400px]',
            typeClasses[toast.type]
          ]"
        >
          <component
            :is="typeIcons[toast.type]"
            class="w-5 h-5 flex-shrink-0"
          />
          
          <p class="text-sm font-medium flex-1">{{ toast.message }}</p>
          
          <button
            @click="removeToast(toast.id)"
            class="p-1 rounded hover:bg-white/10 transition-colors"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { CheckCircle, AlertCircle, AlertTriangle, Info, X } from 'lucide-vue-next'
import { toasts, useToast } from '@/composables/useToast'

const { remove: removeToast } = useToast()

const typeClasses = {
  success: 'bg-surface border-success/30 text-success',
  error: 'bg-surface border-error/30 text-error',
  warning: 'bg-surface border-warning/30 text-warning',
  info: 'bg-surface border-primary/30 text-primary'
}

const typeIcons = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info
}
</script>
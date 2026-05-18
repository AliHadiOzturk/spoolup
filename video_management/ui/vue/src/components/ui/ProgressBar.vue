<template>
  <div class="w-full">
    <div class="flex items-center justify-between mb-1.5">
      <span class="text-sm text-text-secondary">{{ label }}</span>
      <span class="text-sm font-medium text-text-primary">{{ percentage }}%</span>
    </div>
    
    <div class="w-full h-2 bg-surface-elevated rounded-full overflow-hidden">
      <div
        :class="[
          'h-full rounded-full transition-all duration-500 ease-out',
          variantClasses[variant]
        ]"
        :style="{ width: `${percentage}%` }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  value: number
  max?: number
  label?: string
  variant?: 'primary' | 'success' | 'warning' | 'error'
}

const props = withDefaults(defineProps<Props>(), {
  max: 100,
  variant: 'primary'
})

const percentage = computed(() => {
  return Math.min(100, Math.max(0, Math.round((props.value / props.max) * 100)))
})

const variantClasses = {
  primary: 'bg-primary',
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-error'
}
</script>
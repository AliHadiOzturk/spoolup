<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :class="[
      'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-200',
      variantClasses[variant],
      sizeClasses[size],
      { 'opacity-50 cursor-not-allowed': disabled || loading }
    ]"
    @click="$emit('click', $event)"
  >
    <Loader2
      v-if="loading"
      class="w-4 h-4 animate-spin"
    />
    <slot />
  </button>
</template>

<script setup lang="ts">
import { Loader2 } from 'lucide-vue-next'

interface Props {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  type?: 'button' | 'submit' | 'reset'
  disabled?: boolean
  loading?: boolean
}

withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  type: 'button',
  disabled: false,
  loading: false
})

defineEmits<{ click: [event: MouseEvent] }>()

const variantClasses = {
  primary: 'bg-primary text-white hover:bg-primary-hover hover:shadow-lg hover:shadow-primary/25 active:scale-95',
  secondary: 'bg-surface-elevated text-text-primary border border-border hover:bg-surface-hover hover:border-border/80 active:scale-95',
  ghost: 'text-text-secondary hover:text-text-primary hover:bg-surface-elevated active:scale-95',
  danger: 'bg-error/10 text-error hover:bg-error/20 active:scale-95'
}

const sizeClasses = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2.5 text-sm',
  lg: 'px-6 py-3 text-base'
}
</script>
<template>
  <span
    :class="[
      'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium',
      variantClasses[variant]
    ]"
  >
    <span
      v-if="dot"
      :class="[
        'w-1.5 h-1.5 rounded-full',
        dotClasses[variant]
      ]"
    />
    <slot />
  </span>
</template>

<script setup lang="ts">
interface Props {
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'error' | 'info'
  dot?: boolean
}

withDefaults(defineProps<Props>(), {
  variant: 'default',
  dot: false
})

const variantClasses = {
  default: 'bg-surface-elevated text-text-secondary border border-border',
  primary: 'bg-primary/10 text-primary border border-primary/20',
  success: 'bg-success/10 text-success border border-success/20',
  warning: 'bg-warning/10 text-warning border border-warning/20',
  error: 'bg-error/10 text-error border border-error/20',
  info: 'bg-secondary/10 text-secondary border border-secondary/20'
}

const dotClasses = {
  default: 'bg-text-secondary',
  primary: 'bg-primary',
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-error',
  info: 'bg-secondary'
}
</script>
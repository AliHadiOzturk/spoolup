<template>
  <Transition
    enter-active-class="transition-opacity duration-200"
    enter-from-class="opacity-0"
    leave-active-class="transition-opacity duration-200"
    leave-to-class="opacity-0"
  >
    <div
      v-if="modelValue"
      class="fixed inset-0 z-50 flex items-center justify-center p-4"
      @click="closeOnBackdrop && $emit('update:modelValue', false)"
    >
      <!-- Backdrop -->
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      
      <!-- Modal content -->
      <div
        :class="['relative bg-surface border border-border rounded-xl shadow-2xl w-full max-h-[90vh] overflow-y-auto', sizeClasses[size]]"
        @click.stop
      >
        <!-- Header -->
        <div
          v-if="title"
          class="flex items-center justify-between p-6 border-b border-border"
        >
          <h3 class="text-lg font-semibold text-text-primary">{{ title }}</h3>
          
          <button
            @click="$emit('update:modelValue', false)"
            class="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
        
        <!-- Body -->
        <div class="p-6">
          <slot />
        </div>
        
        <!-- Footer -->
        <div
          v-if="$slots.footer"
          class="flex items-center justify-end gap-3 p-6 border-t border-border"
        >
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { X } from 'lucide-vue-next'

interface Props {
  modelValue: boolean
  title?: string
  closeOnBackdrop?: boolean
  size?: 'sm' | 'md' | 'lg'
}

withDefaults(defineProps<Props>(), {
  closeOnBackdrop: true,
  size: 'md'
})

const sizeClasses = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-4xl'
}

defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>
<template>
  <div class="space-y-1">
    <label
      v-if="label"
      :for="id"
      class="block text-sm font-medium text-text-secondary"
    >
      {{ label }}
    </label>
    
    <div class="relative">
      <component
        :is="multiline ? 'textarea' : 'input'"
        :id="id"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :rows="multiline ? rows : undefined"
        class="input-field"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
    </div>
    
    <p
      v-if="error"
      class="text-sm text-error"
    >
      {{ error }}
    </p>
  </div>
</template>

<script setup lang="ts">
interface Props {
  modelValue: string
  label?: string
  type?: string
  placeholder?: string
  disabled?: boolean
  error?: string
  multiline?: boolean
  rows?: number
}

withDefaults(defineProps<Props>(), {
  type: 'text',
  disabled: false,
  multiline: false,
  rows: 4
})

defineEmits<{ 'update:modelValue': [value: string] }>()

const id = `input-${Math.random().toString(36).substr(2, 9)}`
</script>
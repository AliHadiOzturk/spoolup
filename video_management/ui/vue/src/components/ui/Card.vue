<template>
  <div
    :class="[
      'bg-surface border border-border rounded-xl overflow-hidden transition-all duration-200',
      { 'card-hover': hoverable }
    ]"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
interface Props {
  hoverable?: boolean
}

withDefaults(defineProps<Props>(), {
  hoverable: true
})
</script>
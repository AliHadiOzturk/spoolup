<template>
  <div class="animate-pulse">
    <div
      :class="[
        'bg-surface-elevated rounded-lg',
        heightClass
      ]"
    />
  </div>
</template>

<script setup lang="ts">
interface Props {
  height?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: 'h-20'
})

const heightClass = props.height
</script>
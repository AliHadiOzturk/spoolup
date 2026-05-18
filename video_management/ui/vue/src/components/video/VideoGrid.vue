<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
    <VideoCard
      v-for="video in videos"
      :key="video.id"
      :video="video"
      :selectable="selectable"
      :selected="selectedIds.has(video.id)"
      @toggle-select="$emit('toggle-select', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import VideoCard from './VideoCard.vue'
import type { Video } from '@/stores/videos'

interface Props {
  videos: Video[]
  selectable?: boolean
  selectedIds?: Set<number>
}

withDefaults(defineProps<Props>(), {
  selectable: false,
  selectedIds: () => new Set()
})

defineEmits<{
  'toggle-select': [id: number]
}>()
</script>
<template>
  <div class="relative aspect-video bg-black rounded-xl overflow-hidden group">
    <video
      ref="videoRef"
      :src="src"
      class="w-full h-full"
      :controls="controls"
      @timeupdate="$emit('timeupdate', $event)"
      @loadedmetadata="$emit('loadedmetadata', $event)"
    />
    
    <!-- Custom controls overlay -->
    <div
      v-if="!controls"
      class="absolute inset-0 flex items-center justify-center bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity"
      @click="togglePlay"
    >
      <button class="w-16 h-16 rounded-full bg-primary/90 flex items-center justify-center backdrop-blur-sm hover:bg-primary transition-colors">
        <Play v-if="!isPlaying" class="w-6 h-6 text-white ml-1" />
        <Pause v-else class="w-6 h-6 text-white" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Play, Pause } from 'lucide-vue-next'

interface Props {
  src: string
  controls?: boolean
}

withDefaults(defineProps<Props>(), {
  controls: true
})

defineEmits<{
  timeupdate: [event: Event]
  loadedmetadata: [event: Event]
}>()

const videoRef = ref<HTMLVideoElement>()
const isPlaying = ref(false)

const togglePlay = () => {
  if (!videoRef.value) return
  
  if (videoRef.value.paused) {
    videoRef.value.play()
    isPlaying.value = true
  } else {
    videoRef.value.pause()
    isPlaying.value = false
  }
}
</script>
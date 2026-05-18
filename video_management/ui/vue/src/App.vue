<template>
  <div id="app" class="min-h-screen bg-background">
    <RouterView />
    <ToastContainer />
  </div>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'
import ToastContainer from './components/ui/ToastContainer.vue'
</script>
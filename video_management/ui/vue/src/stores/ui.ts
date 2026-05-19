import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUIStore = defineStore('ui', () => {
  const sidebarOpen = ref(true)
  const currentPage = ref('')
  const isMobile = ref(false)

  const toggleSidebar = () => {
    sidebarOpen.value = !sidebarOpen.value
  }

  const setCurrentPage = (page: string) => {
    currentPage.value = page
  }

  const checkMobile = () => {
    isMobile.value = window.innerWidth < 768
    if (isMobile.value) {
      sidebarOpen.value = false
    }
  }

  return {
    sidebarOpen,
    currentPage,
    isMobile,
    toggleSidebar,
    setCurrentPage,
    checkMobile
  }
})
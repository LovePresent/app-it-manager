import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'
import type { Category } from '@/types'

export const useCategoryStore = defineStore('category', () => {
  const categories = ref<Category[]>([])
  const loaded = ref(false)

  async function fetchCategories() {
    if (loaded.value) return
    const { data } = await api.get('/categories')
    categories.value = data
    loaded.value = true
  }

  function getCategoryName(id: number): string {
    return categories.value.find((c) => c.id === id)?.name ?? ''
  }

  return { categories, loaded, fetchCategories, getCategoryName }
})

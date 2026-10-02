import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { http, unwrap } from '../api/http'
import type { ApiResponse } from '../types/api'
import { useAuthStore } from './auth'

export interface StoreItem {
  id: number
  store_no: string
  name: string
  address: string | null
  phone: string | null
  is_active: boolean
  timezone: string
}

export const useStoreScope = defineStore('storeScope', () => {
  const auth = useAuthStore()
  const selectedId = ref<number | null>(null)
  const stores = ref<StoreItem[]>([])
  const ownId = computed(() => auth.employee?.store_id ?? null)
  const selected = computed(() => stores.value.find((item) => item.id === selectedId.value) ?? null)
  const canWriteStore = computed(() => auth.employee?.role !== '总部' && selectedId.value === ownId.value)

  async function load() {
    const response = await http.get<ApiResponse<StoreItem[]>>('/stores')
    stores.value = unwrap(response.data)
    const key = `marketflow_selected_store_${auth.employee?.id ?? 'guest'}`
    const saved = Number(localStorage.getItem(key))
    const fallback = ownId.value ?? stores.value.find((item) => item.is_active)?.id ?? null
    const valid = stores.value.some((item) => item.id === saved && item.is_active)
    selectedId.value = valid ? saved : fallback
    if (selectedId.value !== null) localStorage.setItem(key, String(selectedId.value))
  }

  function choose(id: number) {
    if (!stores.value.some((item) => item.id === id && item.is_active)) return
    selectedId.value = id
    localStorage.setItem(`marketflow_selected_store_${auth.employee?.id ?? 'guest'}`, String(id))
  }

  function clear() {
    selectedId.value = null
    stores.value = []
  }

  return { stores, selectedId, selected, ownId, canWriteStore, load, choose, clear }
})

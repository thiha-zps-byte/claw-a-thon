import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getUid, setUid } from '@/api/client'

export const useUserStore = defineStore('user', () => {
  const uid = ref(getUid())

  function changeUid(next: string) {
    setUid(next)
    uid.value = getUid()
  }

  return { uid, changeUid }
})

import { ref } from 'vue'

export type Theme = 'dark' | 'light'

const savedTheme = localStorage.getItem('marketflow_theme')
export const theme = ref<Theme>(savedTheme === 'light' ? 'light' : 'dark')

export function setTheme(value: Theme) {
  theme.value = value
  document.documentElement.dataset.theme = value
  document.documentElement.style.colorScheme = value
  localStorage.setItem('marketflow_theme', value)
}

setTheme(theme.value)

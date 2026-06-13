import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import { definePreset } from '@primevue/themes'
import Aura from '@primevue/themes/aura'
import 'primeicons/primeicons.css'
import './assets/theme.css'
import App from './App.vue'

// GreenNode-inspired green primary palette (light theme).
const GreenNodePreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '#eafaf1',
      100: '#cdf0dc',
      200: '#9fe2bd',
      300: '#67cf98',
      400: '#36b878',
      500: '#1a9d60',
      600: '#0f7f4d',
      700: '#0c6640',
      800: '#0c5135',
      900: '#0a432d',
      950: '#03251a',
    },
  },
})

const app = createApp(App)
app.use(createPinia())
app.use(PrimeVue, {
  theme: {
    preset: GreenNodePreset,
    // Force light mode: this selector is never present on <html>.
    options: { darkModeSelector: '.force-dark-never' },
  },
})
app.use(ToastService)
app.mount('#app')

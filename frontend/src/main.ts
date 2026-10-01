import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import { startTranslation } from './i18n'
import './styles.css'
import './modern.css'
import './light.css'

createApp(App).use(createPinia()).use(router).mount('#app')
startTranslation()

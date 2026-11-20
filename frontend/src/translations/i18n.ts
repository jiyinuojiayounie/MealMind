import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './en.json'
import zhCN from './zh-CN.json'

export const languages = ['zh-CN', 'en'] as const
export type Language = (typeof languages)[number]

const storageKey = 'mealmind.language'

function readLanguage(): Language {
  try {
    const saved = localStorage.getItem(storageKey)
    return languages.find((language) => language === saved) ?? 'zh-CN'
  } catch {
    return 'zh-CN'
  }
}

export async function initializeTranslations() {
  const language = readLanguage()
  document.documentElement.lang = language
  await i18n.use(initReactI18next).init({
    resources: { en: { translation: en }, 'zh-CN': { translation: zhCN } },
    lng: language,
    supportedLngs: [...languages],
    fallbackLng: 'en',
    interpolation: { escapeValue: false },
  })
}

export async function selectLanguage(language: Language) {
  await i18n.changeLanguage(language)
  document.documentElement.lang = language
  try {
    localStorage.setItem(storageKey, language)
  } catch {
    // The current session can still switch languages when storage is blocked.
  }
}

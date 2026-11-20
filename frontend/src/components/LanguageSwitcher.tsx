import { useTranslation } from 'react-i18next'
import { languages, selectLanguage } from '../translations/i18n'

const labels = { 'zh-CN': '中文', en: 'English' }

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation()

  return (
    <div className="language-switcher" role="group" aria-label={t('language')}>
      {languages.map((language) => (
        <button
          key={language}
          type="button"
          lang={language}
          aria-pressed={i18n.resolvedLanguage === language}
          onClick={() => void selectLanguage(language)}
        >
          {labels[language]}
        </button>
      ))}
    </div>
  )
}

import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import { BackendStatus } from '../components/BackendStatus'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { featurePaths } from '../types/navigation'

const tabs = ['today', 'log', 'pantry', 'profile'] as const

export function AppLayout() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const main = useRef<HTMLElement>(null)
  const previousPath = useRef(pathname)

  useEffect(() => {
    if (previousPath.current !== pathname) {
      previousPath.current = pathname
      main.current?.focus()
      window.scrollTo(0, 0)
    }
  }, [pathname])

  return (
    <>
      <a className="skip-link" href="#main-content">{t('skip')}</a>
      <header className="site-header">
        <div className="frame header-inner">
          <Link to="/" className="wordmark">MealMind</Link>
          <LanguageSwitcher />
        </div>
        {import.meta.env.DEV && <BackendStatus />}
      </header>
      <main className="frame content" id="main-content" ref={main} tabIndex={-1}>
        <Outlet />
      </main>
      {pathname !== '/' && (
        <nav className="site-nav" aria-label={t('navigation')}>
          <div className="frame nav-inner">
            {tabs.map((tab) => (
              <NavLink key={tab} to={featurePaths[tab]}>{t(`nav.${tab}`)}</NavLink>
            ))}
          </div>
        </nav>
      )}
    </>
  )
}

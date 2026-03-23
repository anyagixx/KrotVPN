import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  CreditCard,
  LayoutDashboard,
  LogOut,
  Server,
  Settings,
  Shield,
  Users,
} from 'lucide-react'
import { useAuthStore } from '../stores/auth'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Обзор', hint: 'Статистика и состояние' },
  { to: '/users', icon: Users, label: 'Пользователи', hint: 'Аккаунты и роли' },
  { to: '/servers', icon: Server, label: 'Ноды и маршруты', hint: 'Entry, exit и route topology' },
  { to: '/plans', icon: CreditCard, label: 'Тарифы', hint: 'Подписки и цены' },
  { to: '/analytics', icon: BarChart3, label: 'Аналитика', hint: 'Выручка и конверсия' },
  { to: '/settings', icon: Settings, label: 'Настройки', hint: 'Системные параметры' },
]

const pageMeta: Record<string, { title: string; description: string }> = {
  '/': { title: 'Операционный центр', description: 'Контроль подписок, серверов и живого состояния сервиса.' },
  '/users': { title: 'Пользователи', description: 'Поиск, фильтрация и аудит аккаунтов.' },
  '/servers': { title: 'Ноды и маршруты', description: 'Физические узлы и логические цепочки, по которым выдаётся трафик клиентам.' },
  '/plans': { title: 'Тарифы', description: 'Текущие подписки и конфигурация продуктовой линейки.' },
  '/analytics': { title: 'Аналитика', description: 'Ключевые метрики роста и монетизации.' },
  '/settings': { title: 'Настройки', description: 'Базовые параметры инсталляции и реферальной модели.' },
}

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const meta = pageMeta[location.pathname] ?? pageMeta['/']

  return (
    <div className="app-shell">
      <div className="mx-auto grid min-h-[calc(100vh-2rem)] max-w-[1600px] grid-cols-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="glass flex flex-col overflow-hidden">
          <div className="border-b border-white/5 px-6 py-6">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-300/15 text-emerald-200 ring-1 ring-emerald-200/15">
                <Shield className="h-7 w-7" />
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-200/75">KrotVPN</p>
                <h1 className="text-xl font-extrabold">Admin Console</h1>
                <p className="mt-1 text-sm muted">Операционный кабинет сервиса</p>
              </div>
            </div>
          </div>

          <div className="px-4 py-4">
            <div className="panel-soft flex items-center gap-3 px-4 py-3">
              <div className="rounded-2xl bg-cyan-300/10 p-2.5 text-cyan-200">
                <Activity className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold">Контур управления активен</p>
                <p className="text-xs muted">Backend отвечает, админ-маршруты доступны</p>
              </div>
            </div>
          </div>

          <nav className="flex-1 space-y-2 px-4 pb-4">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  [
                    'group flex items-center gap-3 rounded-2xl px-4 py-3 transition',
                    isActive
                      ? 'bg-emerald-300/12 text-emerald-100 ring-1 ring-emerald-200/10'
                      : 'text-slate-300 hover:bg-white/5 hover:text-white',
                  ].join(' ')
                }
              >
                <div className="rounded-xl bg-white/5 p-2 transition group-hover:bg-white/10">
                  <item.icon className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <p className="font-semibold">{item.label}</p>
                  <p className="truncate text-xs muted">{item.hint}</p>
                </div>
              </NavLink>
            ))}
          </nav>

          <div className="border-t border-white/5 px-4 py-4">
            <div className="panel-soft mb-3 flex items-center gap-3 px-4 py-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-lg font-bold text-white">
                {user?.email?.[0]?.toUpperCase() || 'A'}
              </div>
              <div className="min-w-0">
                <p className="truncate font-semibold">{user?.email || 'admin@krotvpn.com'}</p>
                <p className="text-xs uppercase tracking-[0.14em] muted">{user?.role || 'admin'}</p>
              </div>
            </div>

            <button onClick={handleLogout} className="btn-secondary w-full justify-start">
              <LogOut className="h-5 w-5" />
              Выйти
            </button>
          </div>
        </aside>

        <div className="panel overflow-hidden">
          <header className="border-b border-white/5 px-6 py-6 md:px-8">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-200/75">Admin Workspace</p>
                <h2 className="mt-2 text-3xl font-extrabold tracking-tight">{meta.title}</h2>
                <p className="mt-2 max-w-2xl text-sm muted">{meta.description}</p>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className="panel-soft px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.18em] muted">Среда</p>
                  <p className="mt-2 font-semibold text-emerald-200">Production</p>
                </div>
                <div className="panel-soft px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.18em] muted">Роль</p>
                  <p className="mt-2 font-semibold">{user?.role || 'admin'}</p>
                </div>
                <div className="panel-soft px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.18em] muted">Доступ</p>
                  <p className="mt-2 font-semibold text-cyan-100">Secure console</p>
                </div>
              </div>
            </div>
          </header>

          <main className="p-6 md:p-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}

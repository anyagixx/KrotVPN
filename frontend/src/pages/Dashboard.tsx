import { useQuery } from 'react-query'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, ArrowDown, ArrowRightLeft, ArrowUp, Calendar, Clock, Gift, MapPin, Server, Shield, Zap } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { userApi, vpnApi } from '../lib/api'
import Loading from '../components/Loading'

export default function Dashboard() {
  const { t } = useTranslation()
  const { user } = useAuthStore()

  const { data: vpnStats, isLoading: statsLoading, isError: statsError } = useQuery('vpn-stats', () => vpnApi.getStats(), {
    refetchInterval: 10000,
  })

  const { data: userStats, isLoading: userStatsLoading, isError: userStatsError } = useQuery('user-stats', () => userApi.getStats())
  const { data: vpnConfig } = useQuery('vpn-config-summary', () => vpnApi.getConfig(), {
    retry: false,
  })

  if (statsLoading || userStatsLoading) {
    return <Loading text={t('loading')} />
  }

  if (statsError || userStatsError) {
    return (
      <div className="empty-state">
        <AlertTriangle className="h-10 w-10 text-red-200" />
        <div>
          <p className="text-lg font-semibold">Не удалось загрузить сводку</p>
          <p className="mt-1 text-sm muted">Проверь доступность backend или обнови страницу позже.</p>
        </div>
      </div>
    )
  }

  const stats = vpnStats?.data
  const uStats = userStats?.data
  const config = vpnConfig?.data
  const routeName = config?.route_name
  const entryLocation = config?.entry_server_location || stats?.server_location
  const entryName = config?.entry_server_name || stats?.server_name
  const exitName = config?.exit_server_name
  const exitLocation = config?.exit_server_location

  return (
    <div className="content-section animate-in">
      <section className="glass p-6 md:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-100/70">Private dashboard</p>
            <h1 className="mt-3 text-4xl font-extrabold tracking-tight">
              {t('welcome')}, <span className="gradient-text">{user?.display_name || 'User'}</span>
            </h1>
            <p className="mt-3 max-w-2xl text-sm muted">
              Контролируйте статус туннеля, оставшиеся дни подписки и доступ к конфигурации с одного экрана.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="panel-soft px-4 py-4">
              <p className="text-xs uppercase tracking-[0.18em] muted">Подписка</p>
              <p className="mt-2 text-lg font-bold">
                {uStats?.has_active_subscription ? `${uStats.subscription_days_left} ${t('daysLeft')}` : 'Нужна активация'}
              </p>
            </div>
            <div className="panel-soft px-4 py-4">
              <p className="text-xs uppercase tracking-[0.18em] muted">VPN статус</p>
              <p className="mt-2 text-lg font-bold">{stats?.is_connected ? t('connected') : t('disconnected')}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="metric-card">
          <div className="flex items-center justify-between">
            <span className="metric-label">{t('status')}</span>
            <span className={stats?.is_connected ? 'status-badge-success' : 'status-badge-error'}>
              {stats?.is_connected ? 'online' : 'offline'}
            </span>
          </div>
          <div className="mt-5 flex items-center gap-3">
            <div className="rounded-2xl bg-emerald-300/12 p-3 text-emerald-200">
              <Shield className="h-6 w-6" />
            </div>
            <div>
              <p className="font-bold">{stats?.is_connected ? t('connected') : t('disconnected')}</p>
              <p className="text-sm muted">{entryLocation || 'Сервер ещё не назначен'}</p>
            </div>
          </div>
        </div>

        <div className="metric-card">
          <div className="flex items-center justify-between">
            <span className="metric-label">{t('subscription')}</span>
            <Calendar className="h-5 w-5 text-cyan-100" />
          </div>
          <p className="metric-value">{uStats?.has_active_subscription ? uStats.subscription_days_left : 0}</p>
          <p className="mt-2 text-sm muted">
            {uStats?.has_active_subscription ? t('subscriptionActive') : 'Продлите доступ, чтобы получить конфиг'}
          </p>
        </div>

        <div className="metric-card">
          <div className="flex items-center justify-between">
            <span className="metric-label">{t('upload')}</span>
            <ArrowUp className="h-5 w-5 text-emerald-200" />
          </div>
          <p className="metric-value">{stats?.total_upload_formatted || '0 B'}</p>
          <p className="mt-2 text-sm muted">{t('traffic')}</p>
        </div>

        <div className="metric-card">
          <div className="flex items-center justify-between">
            <span className="metric-label">{t('download')}</span>
            <ArrowDown className="h-5 w-5 text-cyan-100" />
          </div>
          <p className="metric-value">{stats?.total_download_formatted || '0 B'}</p>
          <p className="mt-2 text-sm muted">{t('traffic')}</p>
        </div>
      </section>

      {!uStats?.has_active_subscription ? (
        <section className="glass p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-100/70">Next step</p>
              <h2 className="mt-3 text-2xl font-extrabold">Подключите подписку, чтобы получить рабочий конфиг</h2>
              <p className="mt-2 max-w-2xl text-sm muted">
                Пока доступ не активирован, кабинет показывает базовую статистику. После активации появятся `.conf`, QR-код и сервер.
              </p>
            </div>
            <Link to="/subscription" className="btn-primary">
              <Zap className="h-5 w-5" />
              Выбрать тариф
            </Link>
          </div>
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <div className="panel p-6">
          <h2 className="text-xl font-bold">Сервер и соединение</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <div className="panel-soft px-4 py-4">
              <div className="flex items-center gap-3">
                <Server className="h-5 w-5 text-cyan-100" />
                <div>
                  <p className="text-sm muted">Entry node</p>
                  <p className="mt-1 font-semibold">{entryName || 'Ожидает активации'}</p>
                </div>
              </div>
            </div>
            <div className="panel-soft px-4 py-4">
              <div className="flex items-center gap-3">
                <MapPin className="h-5 w-5 text-cyan-100" />
                <div>
                  <p className="text-sm muted">Entry location</p>
                  <p className="mt-1 font-semibold">{entryLocation || 'Не выбрано'}</p>
                </div>
              </div>
            </div>
            <div className="panel-soft px-4 py-4">
              <div className="flex items-center gap-3">
                <ArrowRightLeft className="h-5 w-5 text-cyan-100" />
                <div>
                  <p className="text-sm muted">Маршрут</p>
                  <p className="mt-1 font-semibold">{routeName || 'Legacy single-node'}</p>
                  <p className="mt-1 text-sm muted">
                    {exitName ? `${entryName || 'Entry'} -> ${exitName}` : 'Выходной узел пока не задан'}
                  </p>
                </div>
              </div>
            </div>
            <div className="panel-soft px-4 py-4">
              <div className="flex items-center gap-3">
                <MapPin className="h-5 w-5 text-cyan-100" />
                <div>
                  <p className="text-sm muted">Exit location</p>
                  <p className="mt-1 font-semibold">
                    {exitLocation || 'Не задано'}
                  </p>
                </div>
              </div>
            </div>
            <div className="panel-soft px-4 py-4">
              <div className="flex items-center gap-3">
                <Clock className="h-5 w-5 text-cyan-100" />
                <div>
                  <p className="text-sm muted">{t('lastConnection')}</p>
                  <p className="mt-1 font-semibold">
                    {stats?.last_handshake_at ? new Date(stats.last_handshake_at).toLocaleString('ru-RU') : 'Нет данных'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="glass p-6">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-100/70">Quick actions</p>
          <h2 className="mt-3 text-2xl font-extrabold">Основные действия</h2>
          <div className="mt-6 grid gap-3">
            <Link to="/config" className="btn-secondary justify-start">
              <Shield className="h-5 w-5" />
              Открыть конфигурацию
            </Link>
            <Link to="/subscription" className="btn-primary justify-start">
              <Zap className="h-5 w-5" />
              Продлить или сменить тариф
            </Link>
            <Link to="/referrals" className="btn-secondary justify-start">
              <Gift className="h-5 w-5" />
              Открыть реферальную программу
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}

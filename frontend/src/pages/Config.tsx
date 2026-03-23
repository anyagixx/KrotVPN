import { useEffect, useMemo, useState } from 'react'
import { useQuery } from 'react-query'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, ArrowRightLeft, Check, Download, FileCode2, Monitor, QrCode, Smartphone } from 'lucide-react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { vpnApi } from '../lib/api'
import Loading from '../components/Loading'

export default function Config() {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [showQR, setShowQR] = useState(false)

  const { data: configData, isLoading, error } = useQuery('vpn-config', () => vpnApi.getConfig())
  const { data: qrData, isLoading: qrLoading, error: qrError } = useQuery('vpn-qr', () => vpnApi.getQRCode(), { enabled: showQR })
  const { data: routesData } = useQuery('vpn-routes', () => vpnApi.getRoutes())

  const qrUrl = useMemo(() => {
    if (!qrData?.data) return null
    return URL.createObjectURL(qrData.data)
  }, [qrData?.data])

  useEffect(() => {
    return () => {
      if (qrUrl) {
        URL.revokeObjectURL(qrUrl)
      }
    }
  }, [qrUrl])

  const handleDownload = async () => {
    try {
      const response = await vpnApi.downloadConfig()
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = window.document.createElement('a')
      link.href = url
      link.setAttribute('download', 'krotvpn.conf')
      window.document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      toast.success('Конфиг скачан')
    } catch {
      toast.error(t('error'))
    }
  }

  const handleCopy = async () => {
    if (!configData?.data?.config) {
      toast.error('Конфигурация пока недоступна')
      return
    }
    await navigator.clipboard.writeText(configData.data.config)
    setCopied(true)
    toast.success(t('copied'))
    setTimeout(() => setCopied(false), 2000)
  }

  if (isLoading) {
    return <Loading text={t('loading')} />
  }

  const config = configData?.data
  const requestError = error as any
  const errorMessage = requestError?.response?.data?.detail as string | undefined
  const hasNoConfig = requestError?.response?.status === 404
  const isForbidden = requestError?.response?.status === 403
  const routes = routesData?.data?.routes || []
  const routeName = config?.route_name
  const entryName = config?.entry_server_name || config?.server_name
  const entryLocation = config?.entry_server_location || config?.server_location
  const exitName = config?.exit_server_name
  const exitLocation = config?.exit_server_location

  if (hasNoConfig || isForbidden) {
    return (
      <div className="content-section animate-in">
        <div className="section-header">
          <div>
            <h1 className="section-title">{t('vpnConfig')}</h1>
            <p className="section-subtitle">Конфигурация появится сразу после активации доступа и назначения VPN-клиента.</p>
          </div>
        </div>

        <div className="glass p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-100/70">Configuration unavailable</p>
              <h2 className="mt-3 text-2xl font-extrabold">
                {isForbidden ? 'Доступ к VPN сейчас отключён' : 'Конфигурация ещё не выдана'}
              </h2>
              <p className="mt-2 max-w-2xl text-sm muted">
                {errorMessage || 'Сначала нужен активный доступ, после этого кабинет сможет выдать конфиг и QR-код.'}
              </p>
            </div>
            <Link to="/subscription" className="btn-primary">
              <Download className="h-5 w-5" />
              Открыть подписку
            </Link>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {routes.map((route: any) => (
            <div key={route.id} className="metric-card">
              <div className="flex items-center justify-between">
                <span className="metric-label">Маршрут</span>
                <span className={route.tunnel_status === 'up' ? 'status-badge-success' : 'status-badge-error'}>
                  {route.tunnel_status === 'up' ? 'tunnel up' : route.tunnel_status}
                </span>
              </div>
              <div className="mt-5 flex items-center gap-3">
                <div className="rounded-2xl bg-white/8 p-3 text-cyan-100">
                  <ArrowRightLeft className="h-5 w-5" />
                </div>
                <div>
                  <p className="font-bold">{route.name}</p>
                  <p className="text-sm muted">{route.entry_node_name} -&gt; {route.exit_node_name || 'Exit not set'}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (requestError) {
    return (
      <div className="empty-state">
        <AlertTriangle className="h-10 w-10 text-red-200" />
        <div>
          <p className="text-lg font-semibold">Не удалось загрузить конфигурацию</p>
          <p className="mt-1 text-sm muted">{errorMessage || 'Попробуй обновить страницу чуть позже.'}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="content-section animate-in">
      <div className="section-header">
        <div>
          <h1 className="section-title">{t('vpnConfig')}</h1>
          <p className="section-subtitle">Получите `.conf`, QR-код и короткие инструкции по установке на любое устройство.</p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="panel p-6">
          <div className="mb-5 flex items-center gap-3">
            <div className="rounded-2xl bg-emerald-300/12 p-3 text-emerald-200">
              <Smartphone className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-lg font-bold">Телефон и планшет</h2>
              <p className="text-sm muted">Android и iPhone через QR или импорт файла</p>
            </div>
          </div>
          <ol className="space-y-3 text-sm text-slate-200">
            <li>1. Установите клиент AmneziaWG.</li>
            <li>2. Откройте QR-код или импортируйте конфигурационный файл.</li>
            <li>3. Активируйте профиль и включите туннель.</li>
          </ol>
          <button onClick={() => setShowQR(true)} className="btn-secondary mt-5 w-full">
            <QrCode className="h-5 w-5" />
            Показать QR-код
          </button>
        </div>

        <div className="panel p-6">
          <div className="mb-5 flex items-center gap-3">
            <div className="rounded-2xl bg-cyan-300/12 p-3 text-cyan-100">
              <Monitor className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-lg font-bold">Компьютер</h2>
              <p className="text-sm muted">Windows, macOS и Linux через `.conf`</p>
            </div>
          </div>
          <ol className="space-y-3 text-sm text-slate-200">
            <li>1. Скачайте AmneziaVPN или совместимый клиент.</li>
            <li>2. Импортируйте выданный конфиг.</li>
            <li>3. Сохраните профиль и нажмите подключение.</li>
          </ol>
          <button onClick={handleDownload} className="btn-primary mt-5 w-full">
            <Download className="h-5 w-5" />
            {t('downloadConfig')}
          </button>
        </div>
      </div>

      {showQR ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
          <div className="glass w-full max-w-md p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h3 className="text-xl font-bold">{t('scanQR')}</h3>
                <p className="mt-1 text-sm muted">{t('qrInstructions')}</p>
              </div>
              <button onClick={() => setShowQR(false)} className="btn-secondary px-3 py-2">
                {t('close')}
              </button>
            </div>

            {qrUrl ? (
              <div className="mt-6 rounded-[24px] bg-white p-5">
                <img src={qrUrl} alt="QR Code" className="w-full rounded-2xl" />
              </div>
            ) : qrError ? (
              <div className="empty-state mt-6 min-h-[200px]">
                <AlertTriangle className="h-10 w-10 text-red-200" />
                <div>
                  <p className="text-lg font-semibold">QR-код не удалось получить</p>
                  <p className="mt-1 text-sm muted">
                    {((qrError as any)?.response?.data?.detail as string | undefined) || 'Попробуй скачать `.conf` или повторить позже.'}
                  </p>
                </div>
              </div>
            ) : qrLoading ? (
              <Loading text="Генерируем QR-код..." />
            ) : (
              <Loading text="Подготавливаем данные..." />
            )}
          </div>
        </div>
      ) : null}

      <div className="panel p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-white/8 p-3 text-cyan-100">
              <FileCode2 className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold">Конфигурационный файл</h2>
              <p className="text-sm muted">Готовый конфиг для ручного импорта и резервного копирования.</p>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <button onClick={handleCopy} className="btn-secondary">
              {copied ? <Check className="h-5 w-5 text-emerald-200" /> : <Copy className="h-5 w-5" />}
              {copied ? t('copied') : t('copyConfig')}
            </button>
            <button onClick={handleDownload} className="btn-primary">
              <Download className="h-5 w-5" />
              {t('downloadConfig')}
            </button>
          </div>
        </div>

        <pre className="mt-6 overflow-x-auto rounded-[24px] bg-slate-950/55 p-5 text-sm text-cyan-100">
          {config?.config || 'Конфигурация недоступна'}
        </pre>
      </div>

      {config ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <div className="metric-card">
            <p className="metric-label">Маршрут</p>
            <p className="metric-value text-2xl">{routeName || 'Legacy single-node'}</p>
          </div>
          <div className="metric-card">
            <p className="metric-label">Entry node</p>
            <p className="metric-value text-2xl">{entryName}</p>
          </div>
          <div className="metric-card">
            <p className="metric-label">Entry location</p>
            <p className="metric-value text-2xl">{entryLocation}</p>
          </div>
          <div className="metric-card">
            <p className="metric-label">Exit</p>
            <p className="metric-value text-2xl">{exitName || 'Не задан'}</p>
            <p className="mt-2 text-sm muted">{exitLocation || 'Маршрут ещё не замкнут'}</p>
          </div>
          <div className="metric-card">
            <p className="metric-label">VPN IP</p>
            <p className="metric-value text-2xl">{config.address}</p>
          </div>
        </div>
      ) : null}

      {config ? (
        <div className="panel p-6">
          <div className="mb-5 flex items-center gap-3">
            <div className="rounded-2xl bg-white/8 p-3 text-cyan-100">
              <ArrowRightLeft className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold">Топология маршрута</h2>
              <p className="text-sm muted">Клиент подключается к entry-ноде, а внешний трафик выходит через exit-ноду.</p>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="panel-soft px-4 py-4">
              <p className="text-xs uppercase tracking-[0.18em] muted">Entry</p>
              <p className="mt-2 text-lg font-bold">{entryName}</p>
              <p className="mt-1 text-sm muted">{entryLocation}</p>
            </div>
            <div className="panel-soft px-4 py-4">
              <p className="text-xs uppercase tracking-[0.18em] muted">Route</p>
              <p className="mt-2 text-lg font-bold">{routeName || 'Legacy single-node'}</p>
              <p className="mt-1 text-sm muted">
                {exitName ? `${entryName} -> ${exitName}` : 'Пока используется только entry-узел'}
              </p>
            </div>
            <div className="panel-soft px-4 py-4">
              <p className="text-xs uppercase tracking-[0.18em] muted">Exit</p>
              <p className="mt-2 text-lg font-bold">{exitName || 'Не задан'}</p>
              <p className="mt-1 text-sm muted">{exitLocation || 'Выходной узел не сконфигурирован'}</p>
            </div>
          </div>
        </div>
      ) : null}

      {config ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-2">
          <div className="metric-card">
            <p className="metric-label">Создан</p>
            <p className="metric-value text-2xl">{new Date(config.created_at).toLocaleDateString('ru-RU')}</p>
          </div>
        </div>
      ) : null}
    </div>
  )
}

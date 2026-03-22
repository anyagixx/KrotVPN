import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Lock, Mail, Shield } from 'lucide-react'
import { adminApi } from '../lib/api'
import { useAuthStore } from '../stores/auth'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const { setUser, setToken } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const { data } = await adminApi.login(email, password)
      setToken(data.access_token)

      const userResponse = await adminApi.getCurrentUser()
      const user = userResponse.data

      if (user.role !== 'admin' && user.role !== 'superadmin') {
        setToken(null)
        setError('Доступ запрещён. Требуются права администратора.')
        return
      }

      setUser({
        id: user.id,
        email: user.email ?? '',
        role: user.role,
        is_superuser: user.role === 'superadmin',
      })
      navigate('/')
    } catch (err: any) {
      setToken(null)
      setError(err.response?.data?.detail || 'Ошибка авторизации')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-transparent px-4 py-8">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl grid-cols-1 overflow-hidden rounded-[32px] border border-white/10 bg-slate-950/40 shadow-[0_36px_120px_rgba(2,10,14,0.55)] backdrop-blur-sm lg:grid-cols-[1.15fr_0.85fr]">
        <section className="hidden border-r border-white/5 p-10 lg:flex lg:flex-col lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-3 rounded-full border border-emerald-200/12 bg-emerald-300/10 px-4 py-2 text-sm font-semibold text-emerald-100">
              <Shield className="h-4 w-4" />
              KrotVPN Control Plane
            </div>
            <h1 className="mt-8 max-w-xl text-5xl font-extrabold tracking-tight text-white">
              Админ-панель для живого управления VPN-сервисом
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate-300">
              Мониторинг подписок, пользователей, серверов и системного состояния из одной защищённой консоли.
            </p>
          </div>

          <div className="grid gap-4">
            {[
              ['Пользователи', 'Поиск, роли и оперативный аудит аккаунтов.'],
              ['Серверы', 'Нагрузка, доступность и ёмкость VPN-инфраструктуры.'],
              ['Аналитика', 'Выручка, trial-пул и реферальная конверсия.'],
            ].map(([title, description]) => (
              <div key={title} className="panel-soft p-5">
                <p className="text-lg font-bold">{title}</p>
                <p className="mt-2 text-sm muted">{description}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="flex items-center justify-center p-6 md:p-10">
          <div className="w-full max-w-md">
            <div className="mb-8 text-center lg:text-left">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-[24px] bg-emerald-300/12 text-emerald-200 lg:mx-0">
                <Shield className="h-8 w-8" />
              </div>
              <h2 className="mt-5 text-3xl font-extrabold">Вход в админку</h2>
              <p className="mt-2 text-sm muted">Используй учётную запись администратора KrotVPN.</p>
            </div>

            <form onSubmit={handleSubmit} className="glass space-y-4 p-6">
              <label className="block">
                <span className="mb-2 block text-sm muted">Email</span>
                <div className="relative">
                  <Mail className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-500" />
                  <input
                    type="email"
                    className="input pl-12"
                    placeholder="admin@krotvpn.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-2 block text-sm muted">Пароль</span>
                <div className="relative">
                  <Lock className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-500" />
                  <input
                    type="password"
                    className="input pl-12"
                    placeholder="Введите пароль"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
              </label>

              {error ? <p className="rounded-2xl bg-red-400/10 px-4 py-3 text-sm text-red-100">{error}</p> : null}

              <button type="submit" className="btn-primary w-full py-3.5" disabled={loading}>
                {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
                {loading ? 'Проверяем доступ' : 'Войти в консоль'}
              </button>
            </form>

            <p className="mt-5 text-center text-sm muted lg:text-left">
              Для операционной работы используй только административную учётную запись.
            </p>
          </div>
        </section>
      </div>
    </div>
  )
}

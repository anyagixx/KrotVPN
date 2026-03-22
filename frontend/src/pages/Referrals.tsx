import { useState } from 'react'
import { useQuery } from 'react-query'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Check, Copy, Gift, Link2, Users } from 'lucide-react'
import toast from 'react-hot-toast'
import { referralApi } from '../lib/api'
import Loading from '../components/Loading'

export default function Referrals() {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const { data, isLoading } = useQuery('referrals', () => referralApi.getCode())
  const { data: statsData } = useQuery('referral-stats', () => referralApi.getStats())
  const { data: listData, isError } = useQuery('referral-list', () => referralApi.getList())

  if (isLoading) {
    return <Loading text={t('loading')} />
  }

  const referralCode = data?.data?.code || ''
  const referralLink = `${window.location.origin}/register?ref=${referralCode}`
  const stats = statsData?.data
  const referrals = listData?.data?.items || []

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    toast.success(t('copied'))
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="content-section animate-in">
      <div className="section-header">
        <div>
          <h1 className="section-title">{t('referralProgram')}</h1>
          <p className="section-subtitle">Делитесь ссылкой, приглашайте друзей и получайте продление доступа бонусными днями.</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="metric-card text-center">
          <Users className="mx-auto h-8 w-8 text-cyan-100" />
          <p className="metric-value">{stats?.total_referrals || 0}</p>
          <p className="mt-2 text-sm muted">{t('referralsCount')}</p>
        </div>
        <div className="metric-card text-center">
          <Gift className="mx-auto h-8 w-8 text-emerald-200" />
          <p className="metric-value">{stats?.bonus_days_earned || 0}</p>
          <p className="mt-2 text-sm muted">{t('bonusDays')}</p>
        </div>
      </div>

      <div className="panel p-6">
        <div className="flex items-center gap-3">
          <div className="rounded-2xl bg-white/8 p-3 text-cyan-100">
            <Gift className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold">{t('referralCode')}</h2>
            <p className="text-sm muted">Используйте код в ручных приглашениях или чатах.</p>
          </div>
        </div>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <input type="text" value={referralCode} readOnly className="input font-mono" />
          <button onClick={() => handleCopy(referralCode)} className="btn-secondary sm:min-w-[150px]">
            {copied ? <Check className="h-5 w-5 text-emerald-200" /> : <Copy className="h-5 w-5" />}
            Копировать
          </button>
        </div>
      </div>

      <div className="panel p-6">
        <div className="flex items-center gap-3">
          <div className="rounded-2xl bg-emerald-300/12 p-3 text-emerald-200">
            <Link2 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold">{t('referralLink')}</h2>
            <p className="text-sm muted">Полная ссылка на регистрацию с уже подставленным кодом.</p>
          </div>
        </div>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <input type="text" value={referralLink} readOnly className="input font-mono text-sm" />
          <button onClick={() => handleCopy(referralLink)} className="btn-primary sm:min-w-[170px]">
            <Copy className="h-5 w-5" />
            Копировать ссылку
          </button>
        </div>
      </div>

      <div className="glass p-6 text-center">
        <Gift className="mx-auto h-12 w-12 text-emerald-100" />
        <h3 className="mt-4 text-2xl font-extrabold">{t('referralBonus', { days: 7 })}</h3>
        <p className="mt-2 text-sm text-slate-100">Каждый оплаченный реферал приносит тебе дополнительные 7 дней доступа.</p>
      </div>

      {isError ? (
        <div className="empty-state">
          <AlertTriangle className="h-10 w-10 text-red-200" />
          <div>
            <p className="text-lg font-semibold">Не удалось загрузить историю рефералов</p>
            <p className="mt-1 text-sm muted">Основной код работает, но список приглашений временно недоступен.</p>
          </div>
        </div>
      ) : referrals.length > 0 ? (
        <div className="panel p-6">
          <h2 className="text-xl font-bold">Последние приглашения</h2>
          <div className="mt-5 space-y-3">
            {referrals.slice(0, 5).map((item) => (
              <div key={item.id} className="panel-soft flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-semibold">Реферал #{item.id}</p>
                  <p className="mt-1 text-sm muted">Создан {new Date(item.created_at).toLocaleDateString('ru-RU')}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={item.bonus_given ? 'status-badge-success' : 'status-badge-warning'}>
                    {item.bonus_given ? `Бонус начислен: +${item.bonus_days} дн.` : 'Ожидает первой оплаты'}
                  </span>
                  {item.first_payment_at ? (
                    <span className="status-badge-success">Оплата {new Date(item.first_payment_at).toLocaleDateString('ru-RU')}</span>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="empty-state">
          <Users className="h-10 w-10 text-cyan-100" />
          <div>
            <p className="text-lg font-semibold">Рефералов пока нет</p>
            <p className="mt-1 text-sm muted">Скопируй ссылку выше и отправь её первым приглашённым пользователям.</p>
          </div>
        </div>
      )}
    </div>
  )
}

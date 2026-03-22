import { useQuery } from 'react-query'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Check, Crown, Rocket, ShieldCheck, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { billingApi } from '../lib/api'
import Loading from '../components/Loading'

const planIcons = {
  basic: Zap,
  pro: Crown,
  premium: Rocket,
}

export default function Subscription() {
  const { t } = useTranslation()

  const { data: plansData, isLoading: plansLoading, isError: plansError } = useQuery('plans', () => billingApi.getPlans())
  const { data: subData, isLoading: subLoading, isError: subError } = useQuery('subscription', () => billingApi.getSubscription())

  if (plansLoading || subLoading) {
    return <Loading text={t('loading')} />
  }

  if (plansError || subError) {
    return (
      <div className="empty-state">
        <AlertTriangle className="h-10 w-10 text-red-200" />
        <div>
          <p className="text-lg font-semibold">Не удалось загрузить тарифы</p>
          <p className="mt-1 text-sm muted">Сервис оплаты или backend сейчас недоступен. Попробуй позже.</p>
        </div>
      </div>
    )
  }

  const plans = plansData?.data || []
  const subscription = subData?.data

  const handleSubscribe = async (planId: number) => {
    try {
      const { data } = await billingApi.createPayment(planId)
      if (data.payment_url) {
        window.location.href = data.payment_url
      }
    } catch {
      toast.error(t('error'))
    }
  }

  return (
    <div className="content-section animate-in">
      <div className="section-header">
        <div>
          <h1 className="section-title">{t('plans')}</h1>
          <p className="section-subtitle">Выберите план, который подходит по длительности и уровню использования.</p>
        </div>
      </div>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <div className="glass p-6">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-100/70">Текущий статус</p>
          <h2 className="mt-3 text-2xl font-extrabold">
            {subscription?.has_subscription ? subscription.plan_name || 'Активная подписка' : 'Подписка ещё не активирована'}
          </h2>
          <p className="mt-2 text-sm muted">
            {subscription?.has_subscription
              ? `До окончания осталось ${subscription.days_left} дней.`
              : 'После покупки вы сразу попадёте на оплату и получите доступ к конфигурации.'}
          </p>
        </div>

        <div className="panel p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-emerald-300/12 p-3 text-emerald-200">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-lg font-bold">Что включено</h3>
              <p className="text-sm muted">Все планы дают доступ к защищённому туннелю и личному кабинету.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {plans.map((plan, index) => {
          const Icon = planIcons[plan.name.toLowerCase() as keyof typeof planIcons] || Zap
          const isPopular = index === 1

          return (
            <div key={plan.id} className={`panel relative p-6 ${isPopular ? 'ring-1 ring-emerald-200/16' : ''}`}>
              {isPopular ? (
                <div className="absolute right-5 top-5 status-badge-success">
                  Популярный
                </div>
              ) : null}

              <div className="rounded-3xl bg-white/5 p-4">
                <div className={`inline-flex rounded-2xl p-3 ${isPopular ? 'gradient-bg text-slate-950' : 'bg-white/8 text-cyan-100'}`}>
                  <Icon className="h-7 w-7" />
                </div>
                <h3 className="mt-5 text-2xl font-extrabold">{plan.name}</h3>
                <div className="mt-3 flex items-end gap-2">
                  <span className="text-4xl font-extrabold">{plan.price}₽</span>
                  <span className="pb-1 text-sm muted">
                    / {plan.duration_days} {t('days')}
                  </span>
                </div>
              </div>

              <ul className="mt-6 space-y-3">
                {plan.features?.map((feature: string, i: number) => (
                  <li key={i} className="flex items-start gap-3 text-sm text-slate-100">
                    <div className="mt-0.5 rounded-full bg-emerald-300/12 p-1 text-emerald-200">
                      <Check className="h-3.5 w-3.5" />
                    </div>
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              <button onClick={() => handleSubscribe(plan.id)} className={`mt-6 w-full ${isPopular ? 'btn-primary' : 'btn-secondary'}`}>
                {subscription?.has_subscription ? t('extend') : t('buy')}
              </button>
            </div>
          )
        })}
      </section>

      {plans.length === 0 ? (
        <div className="empty-state">
          <ShieldCheck className="h-10 w-10 text-cyan-100" />
          <div>
            <p className="text-lg font-semibold">Активные планы пока не опубликованы</p>
            <p className="mt-1 text-sm muted">Когда администратор добавит тарифы, они появятся здесь автоматически.</p>
          </div>
        </div>
      ) : null}

      {!subscription?.has_subscription ? (
        <section className="glass p-6 text-center">
          <h3 className="text-2xl font-extrabold">{t('trial')}</h3>
          <p className="mt-2 text-sm text-slate-100">{t('trialDays', { days: 3 })} и быстрый вход в личный кабинет.</p>
        </section>
      ) : null}
    </div>
  )
}

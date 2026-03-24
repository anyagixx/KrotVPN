import { FormEvent, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from 'react-query'
import { Activity, RefreshCw, Save, Search, ShieldAlert, Trash2 } from 'lucide-react'
import { adminApi } from '../lib/api'

type RouteTarget = 'ru' | 'de' | 'direct' | 'default'

function targetOptions(): RouteTarget[] {
  return ['ru', 'de', 'direct', 'default']
}

function targetTone(target?: string) {
  if (target === 'ru') return 'metric-pill'
  if (target === 'de') return 'warning-pill'
  if (target === 'direct') return 'danger-pill'
  return 'metric-pill'
}

function decisionTone(reason?: string) {
  if (reason?.includes('domain')) return 'metric-pill'
  if (reason === 'dns_bound_ip') return 'warning-pill'
  if (reason === 'cidr_rule') return 'warning-pill'
  return 'danger-pill'
}

function prettyReason(reason?: string) {
  return reason?.split('_').join(' ') || 'unknown'
}

function emptyDomainForm() {
  return {
    domain: '',
    route_target: 'de' as RouteTarget,
    priority: 100,
    description: '',
  }
}

function emptyCidrForm() {
  return {
    cidr: '',
    route_target: 'ru' as RouteTarget,
    priority: 100,
    description: '',
  }
}

export default function Settings() {
  const queryClient = useQueryClient()
  const [domainForm, setDomainForm] = useState(emptyDomainForm())
  const [cidrForm, setCidrForm] = useState(emptyCidrForm())
  const [explainAddress, setExplainAddress] = useState('')
  const [domainError, setDomainError] = useState('')
  const [cidrError, setCidrError] = useState('')
  const [explainError, setExplainError] = useState('')
  const [explainResult, setExplainResult] = useState<any>(null)

  const { data: domainRules, isLoading: domainLoading } = useQuery(
    'routing-policy-domains',
    () => adminApi.getDomainRouteRules()
  )
  const { data: cidrRules, isLoading: cidrLoading } = useQuery(
    'routing-policy-cidrs',
    () => adminApi.getCidrRouteRules()
  )
  const { data: dnsBindings, isLoading: dnsLoading } = useQuery(
    'routing-policy-dns-bindings',
    () => adminApi.getPolicyDnsBindings(),
    { refetchInterval: 30000 }
  )

  const refreshPolicyQueries = async () => {
    await Promise.all([
      queryClient.invalidateQueries('routing-policy-domains'),
      queryClient.invalidateQueries('routing-policy-cidrs'),
      queryClient.invalidateQueries('routing-policy-dns-bindings'),
    ])
  }

  const createDomainMutation = useMutation(
    (payload: typeof domainForm) => adminApi.createDomainRouteRule(payload),
    {
      onSuccess: async () => {
        await refreshPolicyQueries()
        setDomainForm(emptyDomainForm())
        setDomainError('')
      },
    }
  )

  const toggleDomainMutation = useMutation(
    ({ id, is_active }: { id: number; is_active: boolean }) =>
      adminApi.updateDomainRouteRule(id, { is_active }),
    {
      onSuccess: refreshPolicyQueries,
    }
  )

  const deleteDomainMutation = useMutation(
    (id: number) => adminApi.deleteDomainRouteRule(id),
    { onSuccess: refreshPolicyQueries }
  )

  const createCidrMutation = useMutation(
    (payload: typeof cidrForm) => adminApi.createCidrRouteRule(payload),
    {
      onSuccess: async () => {
        await refreshPolicyQueries()
        setCidrForm(emptyCidrForm())
        setCidrError('')
      },
    }
  )

  const toggleCidrMutation = useMutation(
    ({ id, is_active }: { id: number; is_active: boolean }) =>
      adminApi.updateCidrRouteRule(id, { is_active }),
    {
      onSuccess: refreshPolicyQueries,
    }
  )

  const deleteCidrMutation = useMutation(
    (id: number) => adminApi.deleteCidrRouteRule(id),
    { onSuccess: refreshPolicyQueries }
  )

  const explainMutation = useMutation(
    (address: string) => adminApi.explainRouteDecision(address),
    {
      onSuccess: (response) => {
        setExplainResult(response.data)
        setExplainError('')
      },
    }
  )

  const ruleCounts = useMemo(() => {
    const domainItems = domainRules?.data || []
    const cidrItems = cidrRules?.data || []
    return {
      domainActive: domainItems.filter((item: any) => item.is_active).length,
      cidrActive: cidrItems.filter((item: any) => item.is_active).length,
      dnsBindings: dnsBindings?.data?.length || 0,
    }
  }, [cidrRules?.data, dnsBindings?.data, domainRules?.data])

  const submitDomainRule = async (event: FormEvent) => {
    event.preventDefault()
    setDomainError('')
    try {
      await createDomainMutation.mutateAsync({
        ...domainForm,
        priority: Number(domainForm.priority),
      })
    } catch (error: any) {
      setDomainError(error?.response?.data?.detail || 'Не удалось сохранить domain rule')
    }
  }

  const submitCidrRule = async (event: FormEvent) => {
    event.preventDefault()
    setCidrError('')
    try {
      await createCidrMutation.mutateAsync({
        ...cidrForm,
        priority: Number(cidrForm.priority),
      })
    } catch (error: any) {
      setCidrError(error?.response?.data?.detail || 'Не удалось сохранить CIDR rule')
    }
  }

  const submitExplain = async (event: FormEvent) => {
    event.preventDefault()
    setExplainError('')
    setExplainResult(null)
    try {
      await explainMutation.mutateAsync(explainAddress)
    } catch (error: any) {
      setExplainError(error?.response?.data?.detail || 'Не удалось объяснить routing decision')
    }
  }

  const isLoading = domainLoading || cidrLoading || dnsLoading
  const domainItems = domainRules?.data || []
  const cidrItems = cidrRules?.data || []
  const dnsItems = dnsBindings?.data || []

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <h1 className="page-title">Routing policy</h1>
          <p className="page-subtitle">
            Preferred control surface для domain/CIDR policy, DNS bindings и explainable routing decisions.
          </p>
        </div>
        <button className="btn-secondary" onClick={() => refreshPolicyQueries()}>
          <RefreshCw className="h-5 w-5" />
          Обновить policy
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="panel p-5">
          <p className="text-xs uppercase tracking-[0.18em] muted">Domain rules</p>
          <p className="mt-3 text-3xl font-bold">{ruleCounts.domainActive}</p>
          <p className="mt-2 text-sm muted">Активных exact и wildcard правил</p>
        </div>
        <div className="panel p-5">
          <p className="text-xs uppercase tracking-[0.18em] muted">CIDR rules</p>
          <p className="mt-3 text-3xl font-bold">{ruleCounts.cidrActive}</p>
          <p className="mt-2 text-sm muted">Активных IP/CIDR overrides</p>
        </div>
        <div className="panel p-5">
          <p className="text-xs uppercase tracking-[0.18em] muted">DNS bindings</p>
          <p className="mt-3 text-3xl font-bold">{ruleCounts.dnsBindings}</p>
          <p className="mt-2 text-sm muted">Живых TTL-bound записей</p>
        </div>
      </div>

      <div className="glass p-6">
        <div className="flex items-start gap-4">
          <div className="rounded-2xl bg-yellow-300/12 p-3 text-yellow-100">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">Preferred operator surface</h3>
            <p className="mt-2 text-sm muted">
              Backend теперь поддерживает CRUD для routing policy rules, explain endpoint и DNS binding inspection.
              Этот экран теперь является основной точкой управления routing policy, а legacy custom routes
              сохраняются только как compatibility fallback в runtime.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="panel p-6">
          <h3 className="text-lg font-semibold">Новый domain rule</h3>
          <form className="mt-5 space-y-4" onSubmit={submitDomainRule}>
            <label className="block">
              <span className="mb-2 block text-sm muted">Домен</span>
              <input
                className="input"
                value={domainForm.domain}
                onChange={(event) => setDomainForm((state) => ({ ...state, domain: event.target.value }))}
                placeholder="*.youtube.com"
              />
            </label>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-2 block text-sm muted">Route target</span>
                <select
                  className="input"
                  value={domainForm.route_target}
                  onChange={(event) => setDomainForm((state) => ({ ...state, route_target: event.target.value as RouteTarget }))}
                >
                  {targetOptions().map((target) => (
                    <option key={target} value={target}>{target.toUpperCase()}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-2 block text-sm muted">Priority</span>
                <input
                  className="input"
                  type="number"
                  value={domainForm.priority}
                  onChange={(event) => setDomainForm((state) => ({ ...state, priority: Number(event.target.value) }))}
                />
              </label>
            </div>
            <label className="block">
              <span className="mb-2 block text-sm muted">Описание</span>
              <input
                className="input"
                value={domainForm.description}
                onChange={(event) => setDomainForm((state) => ({ ...state, description: event.target.value }))}
                placeholder="foreign streaming"
              />
            </label>
            {domainError ? <p className="text-sm text-rose-300">{domainError}</p> : null}
            <button className="btn-primary" type="submit" disabled={createDomainMutation.isLoading}>
              <Save className="h-5 w-5" />
              Сохранить domain rule
            </button>
          </form>
        </section>

        <section className="panel p-6">
          <h3 className="text-lg font-semibold">Новый CIDR rule</h3>
          <form className="mt-5 space-y-4" onSubmit={submitCidrRule}>
            <label className="block">
              <span className="mb-2 block text-sm muted">CIDR или IP</span>
              <input
                className="input"
                value={cidrForm.cidr}
                onChange={(event) => setCidrForm((state) => ({ ...state, cidr: event.target.value }))}
                placeholder="77.88.8.0/24"
              />
            </label>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-2 block text-sm muted">Route target</span>
                <select
                  className="input"
                  value={cidrForm.route_target}
                  onChange={(event) => setCidrForm((state) => ({ ...state, route_target: event.target.value as RouteTarget }))}
                >
                  {targetOptions().map((target) => (
                    <option key={target} value={target}>{target.toUpperCase()}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-2 block text-sm muted">Priority</span>
                <input
                  className="input"
                  type="number"
                  value={cidrForm.priority}
                  onChange={(event) => setCidrForm((state) => ({ ...state, priority: Number(event.target.value) }))}
                />
              </label>
            </div>
            <label className="block">
              <span className="mb-2 block text-sm muted">Описание</span>
              <input
                className="input"
                value={cidrForm.description}
                onChange={(event) => setCidrForm((state) => ({ ...state, description: event.target.value }))}
                placeholder="force RU path"
              />
            </label>
            {cidrError ? <p className="text-sm text-rose-300">{cidrError}</p> : null}
            <button className="btn-primary" type="submit" disabled={createCidrMutation.isLoading}>
              <Save className="h-5 w-5" />
              Сохранить CIDR rule
            </button>
          </form>
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <section className="panel p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold">Активные и отключенные rules</h3>
              <p className="mt-2 text-sm muted">
                Список policy entities из backend CRUD с быстрым toggle/delete управлением.
              </p>
            </div>
            <span className="metric-pill">{isLoading ? 'loading' : `${domainItems.length + cidrItems.length} total`}</span>
          </div>

          <div className="mt-5 grid gap-4 xl:grid-cols-2">
            <div className="space-y-3">
              <h4 className="text-sm font-semibold uppercase tracking-[0.18em] muted">Domain rules</h4>
              {domainItems.map((rule: any) => (
                <div key={`domain-${rule.id}`} className="panel-soft p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold">{rule.domain}</p>
                      <p className="mt-1 text-xs muted">
                        normalized: {rule.normalized_domain} · priority {rule.priority}
                      </p>
                    </div>
                    <span className={targetTone(rule.route_target)}>{String(rule.route_target).toUpperCase()}</span>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      className="btn-secondary"
                      onClick={() => toggleDomainMutation.mutate({ id: rule.id, is_active: !rule.is_active })}
                    >
                      <Activity className="h-4 w-4" />
                      {rule.is_active ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={() => deleteDomainMutation.mutate(rule.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              {!domainItems.length ? <p className="text-sm muted">Пока нет domain rules.</p> : null}
            </div>

            <div className="space-y-3">
              <h4 className="text-sm font-semibold uppercase tracking-[0.18em] muted">CIDR rules</h4>
              {cidrItems.map((rule: any) => (
                <div key={`cidr-${rule.id}`} className="panel-soft p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold">{rule.cidr}</p>
                      <p className="mt-1 text-xs muted">
                        normalized: {rule.normalized_cidr} · priority {rule.priority}
                      </p>
                    </div>
                    <span className={targetTone(rule.route_target)}>{String(rule.route_target).toUpperCase()}</span>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      className="btn-secondary"
                      onClick={() => toggleCidrMutation.mutate({ id: rule.id, is_active: !rule.is_active })}
                    >
                      <Activity className="h-4 w-4" />
                      {rule.is_active ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={() => deleteCidrMutation.mutate(rule.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              {!cidrItems.length ? <p className="text-sm muted">Пока нет CIDR rules.</p> : null}
            </div>
          </div>
        </section>

        <section className="panel p-6">
          <h3 className="text-lg font-semibold">Explain routing decision</h3>
          <p className="mt-2 text-sm muted">
            Проверка effective route target для домена или IP без ручного reasoning в голове.
          </p>

          <form className="mt-5 space-y-4" onSubmit={submitExplain}>
            <label className="block">
              <span className="mb-2 block text-sm muted">Domain or IP</span>
              <input
                className="input"
                value={explainAddress}
                onChange={(event) => setExplainAddress(event.target.value)}
                placeholder="stream.example.com"
              />
            </label>
            {explainError ? <p className="text-sm text-rose-300">{explainError}</p> : null}
            <button className="btn-primary" type="submit" disabled={explainMutation.isLoading}>
              <Search className="h-5 w-5" />
              Explain
            </button>
          </form>

          {explainResult ? (
            <div className="mt-5 panel-soft p-4">
              <div className="flex items-center gap-2">
                <span className={targetTone(explainResult.route_target)}>{String(explainResult.route_target).toUpperCase()}</span>
                <span className={decisionTone(explainResult.decision_reason)}>{prettyReason(explainResult.decision_reason)}</span>
              </div>
              <dl className="mt-4 space-y-2 text-sm">
                <div className="flex items-center justify-between gap-4">
                  <dt className="muted">Trace marker</dt>
                  <dd className="font-mono text-xs">{explainResult.trace_marker}</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt className="muted">Rule ID</dt>
                  <dd>{explainResult.rule_id ?? 'n/a'}</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt className="muted">Normalized domain</dt>
                  <dd>{explainResult.normalized_domain || 'n/a'}</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt className="muted">Resolved IP</dt>
                  <dd>{explainResult.resolved_ip || 'n/a'}</dd>
                </div>
              </dl>
            </div>
          ) : null}

          <div className="mt-6">
            <h4 className="text-sm font-semibold uppercase tracking-[0.18em] muted">Active DNS bindings</h4>
            <div className="mt-3 space-y-3">
              {dnsItems.map((binding: any) => (
                <div key={`${binding.normalized_domain}-${binding.resolved_ip}`} className="panel-soft p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold">{binding.normalized_domain}</p>
                      <p className="mt-1 text-xs muted">{binding.resolved_ip}</p>
                    </div>
                    <span className={targetTone(binding.route_target)}>{String(binding.route_target).toUpperCase()}</span>
                  </div>
                </div>
              ))}
              {!dnsItems.length ? <p className="text-sm muted">Активных DNS bindings пока нет.</p> : null}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

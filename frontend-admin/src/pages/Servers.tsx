import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from 'react-query'
import {
  Activity,
  ArrowRightLeft,
  Edit,
  Globe2,
  MapPin,
  Plus,
  Server,
  ShieldCheck,
  Trash2,
  Users,
} from 'lucide-react'
import { adminApi } from '../lib/api'

function getLoadTone(load?: number) {
  if ((load || 0) >= 80) return 'danger-pill'
  if ((load || 0) >= 50) return 'warning-pill'
  return 'metric-pill'
}

function getNodeRoleTone(role?: string) {
  if (role === 'exit') return 'warning-pill'
  if (role === 'combined') return 'danger-pill'
  return 'metric-pill'
}

function getNodeRoleLabel(role?: string) {
  if (role === 'exit') return 'exit'
  if (role === 'combined') return 'combined'
  return 'entry'
}

function getTunnelTone(status?: string) {
  if (status === 'up') return 'metric-pill'
  if (status === 'not_configured') return 'warning-pill'
  return 'danger-pill'
}

function getTunnelLabel(status?: string) {
  if (status === 'up') return 'tunnel up'
  if (status === 'down') return 'tunnel down'
  if (status === 'no_connectivity') return 'no connectivity'
  if (status === 'not_configured') return 'exit missing'
  return status || 'unknown'
}

function emptyNodeForm() {
  return {
    name: '',
    role: 'entry',
    country_code: 'RU',
    location: '',
    endpoint: '',
    port: 51821,
    public_key: '',
    private_key: '',
    is_active: true,
    is_online: true,
    max_clients: 100,
  }
}

function emptyRouteForm() {
  return {
    name: '',
    entry_node_id: '',
    exit_node_id: '',
    is_active: true,
    is_default: false,
    priority: 100,
    max_clients: '',
  }
}

export default function Servers() {
  const [showNodeModal, setShowNodeModal] = useState(false)
  const [showRouteModal, setShowRouteModal] = useState(false)
  const [editingNode, setEditingNode] = useState<any>(null)
  const [editingRoute, setEditingRoute] = useState<any>(null)
  const [nodeError, setNodeError] = useState('')
  const [routeError, setRouteError] = useState('')
  const [nodeForm, setNodeForm] = useState<any>(emptyNodeForm())
  const [routeForm, setRouteForm] = useState<any>(emptyRouteForm())
  const queryClient = useQueryClient()

  const { data: nodes, isLoading: nodesLoading } = useQuery('admin-nodes', () => adminApi.getNodes())
  const { data: routes, isLoading: routesLoading } = useQuery('admin-routes', () => adminApi.getRoutes())

  const saveNodeMutation = useMutation(({ id, data }: any) => (
    id ? adminApi.updateNode(id, data) : adminApi.createNode(data)
  ), {
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries('admin-nodes'),
        queryClient.invalidateQueries('admin-routes'),
      ])
      setShowNodeModal(false)
      setEditingNode(null)
      setNodeForm(emptyNodeForm())
      setNodeError('')
    },
  })
  const deleteNodeMutation = useMutation((id: number) => adminApi.deleteNode(id), {
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries('admin-nodes'),
        queryClient.invalidateQueries('admin-routes'),
      ])
    },
  })
  const saveRouteMutation = useMutation(({ id, data }: any) => (
    id ? adminApi.updateRoute(id, data) : adminApi.createRoute(data)
  ), {
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries('admin-routes'),
        queryClient.invalidateQueries('admin-nodes'),
      ])
      setShowRouteModal(false)
      setEditingRoute(null)
      setRouteForm(emptyRouteForm())
      setRouteError('')
    },
  })
  const deleteRouteMutation = useMutation((id: number) => adminApi.deleteRoute(id), {
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries('admin-routes'),
        queryClient.invalidateQueries('admin-nodes'),
      ])
    },
  })

  const nodeItems = nodes?.data?.nodes || []
  const routeItems = routes?.data?.routes || []
  const isLoading = nodesLoading || routesLoading

  const onlineCount = nodeItems.filter((node: any) => node.is_online).length
  const activeRoutes = routeItems.filter((route: any) => route.is_active).length
  const entryNodes = useMemo(() => nodeItems.filter((node: any) => node.is_entry_node), [nodeItems])
  const exitNodes = useMemo(() => nodeItems.filter((node: any) => node.is_exit_node), [nodeItems])

  const openNodeCreate = () => {
    setEditingNode(null)
    setNodeForm(emptyNodeForm())
    setNodeError('')
    setShowNodeModal(true)
  }

  const openNodeEdit = (node: any) => {
    setEditingNode(node)
    setNodeForm({
      name: node.name,
      role: node.role,
      country_code: node.country_code,
      location: node.location,
      endpoint: node.endpoint,
      port: node.port,
      public_key: node.public_key || '',
      private_key: '',
      is_active: node.is_active,
      is_online: node.is_online,
      max_clients: node.max_clients,
    })
    setNodeError('')
    setShowNodeModal(true)
  }

  const openRouteCreate = () => {
    setEditingRoute(null)
    setRouteForm(emptyRouteForm())
    setRouteError('')
    setShowRouteModal(true)
  }

  const openRouteEdit = (route: any) => {
    setEditingRoute(route)
    setRouteForm({
      name: route.name,
      entry_node_id: String(route.entry_node_id),
      exit_node_id: route.exit_node_id ? String(route.exit_node_id) : '',
      is_active: route.is_active,
      is_default: route.is_default,
      priority: route.priority,
      max_clients: route.max_clients,
    })
    setRouteError('')
    setShowRouteModal(true)
  }

  const handleDeleteNode = async (node: any) => {
    if (confirm(`Удалить node ${node.name}?`)) {
      await deleteNodeMutation.mutateAsync(node.id)
    }
  }

  const handleDeleteRoute = async (route: any) => {
    if (confirm(`Удалить route ${route.name}?`)) {
      await deleteRouteMutation.mutateAsync(route.id)
    }
  }

  const submitNode = async () => {
    setNodeError('')
    try {
      const payload = {
        ...nodeForm,
        country_code: String(nodeForm.country_code || '').toUpperCase(),
        port: Number(nodeForm.port),
        max_clients: Number(nodeForm.max_clients),
      }
      await saveNodeMutation.mutateAsync({
        id: editingNode?.id,
        data: payload,
      })
    } catch (error: any) {
      setNodeError(error?.response?.data?.detail || 'Не удалось сохранить node')
    }
  }

  const submitRoute = async () => {
    setRouteError('')
    try {
      const payload: any = {
        ...routeForm,
        entry_node_id: Number(routeForm.entry_node_id),
        exit_node_id: routeForm.exit_node_id ? Number(routeForm.exit_node_id) : null,
        priority: Number(routeForm.priority),
        is_active: !!routeForm.is_active,
        is_default: !!routeForm.is_default,
      }

      if (routeForm.max_clients !== '' && routeForm.max_clients !== null) {
        payload.max_clients = Number(routeForm.max_clients)
      } else {
        delete payload.max_clients
      }

      await saveRouteMutation.mutateAsync({
        id: editingRoute?.id,
        data: payload,
      })
    } catch (error: any) {
      setRouteError(error?.response?.data?.detail || 'Не удалось сохранить route')
    }
  }

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <h1 className="page-title">Ноды и маршруты</h1>
          <p className="page-subtitle">
            {onlineCount} из {nodeItems.length} нод онлайн, {activeRoutes} активных маршрутов готовы к выдаче клиентам.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="panel-soft px-4 py-3 text-sm">
            <p className="muted">Маршрутов по умолчанию</p>
            <p className="mt-1 font-bold">{routeItems.filter((route: any) => route.is_default).length}</p>
          </div>
          <button onClick={openNodeCreate} className="btn-primary">
            <Plus className="h-5 w-5" />
            Добавить node
          </button>
          <button onClick={openRouteCreate} className="btn-secondary">
            <Plus className="h-5 w-5" />
            Добавить route
          </button>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-4">
        <div className="panel p-5">
          <p className="text-xs uppercase tracking-[0.18em] muted">Entry nodes</p>
          <p className="mt-3 text-3xl font-extrabold">{entryNodes.length}</p>
          <p className="mt-2 text-sm muted">Точки входа для клиентских подключений.</p>
        </div>
        <div className="panel p-5">
          <p className="text-xs uppercase tracking-[0.18em] muted">Exit nodes</p>
          <p className="mt-3 text-3xl font-extrabold">{exitNodes.length}</p>
          <p className="mt-2 text-sm muted">Узлы, через которые выходит внешний трафик.</p>
        </div>
        <div className="panel p-5">
          <p className="text-xs uppercase tracking-[0.18em] muted">Активные маршруты</p>
          <p className="mt-3 text-3xl font-extrabold">{activeRoutes}</p>
          <p className="mt-2 text-sm muted">Route-aware выдача для клиентов и будущего масштабирования.</p>
        </div>
        <div className="panel p-5">
          <p className="text-xs uppercase tracking-[0.18em] muted">Legacy API</p>
          <p className="mt-3 text-3xl font-extrabold">compat</p>
          <p className="mt-2 text-sm muted">`/admin/servers` сохранён только как rollback-слой.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="empty-state">
          <Activity className="h-10 w-10 text-cyan-200" />
          <div>
            <p className="text-lg font-semibold">Собираем topology view</p>
            <p className="mt-1 text-sm muted">Загружаем ноды, маршруты и legacy-совместимый слой.</p>
          </div>
        </div>
      ) : (
        <>
          <section className="space-y-4">
            <div className="flex items-end justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold">Ноды</h2>
                <p className="mt-1 text-sm muted">
                  Физические entry/exit узлы, из которых собираются клиентские маршруты.
                </p>
              </div>
              <button onClick={openNodeCreate} className="btn-primary">
                <Plus className="h-5 w-5" />
                Новая node
              </button>
            </div>

            {nodeItems.length === 0 ? (
              <div className="empty-state">
                <Server className="h-10 w-10 text-cyan-200" />
                <div>
                  <p className="text-lg font-semibold">Ноды ещё не созданы</p>
                  <p className="mt-1 text-sm muted">После bootstrap здесь появятся RU entry и DE exit.</p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {nodeItems.map((node: any) => (
                  <div key={node.id} className="panel p-6">
                    <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                      <div className="flex items-start gap-4">
                        <div
                          className={[
                            'rounded-2xl p-3 ring-1',
                            node.is_online
                              ? 'bg-emerald-300/12 text-emerald-200 ring-emerald-200/10'
                              : 'bg-red-300/12 text-red-200 ring-red-200/10',
                          ].join(' ')}
                        >
                          <Server className="h-6 w-6" />
                        </div>
                        <div>
                          <div className="flex flex-wrap items-center gap-3">
                            <h3 className="text-xl font-bold">{node.name}</h3>
                            <span className={node.is_online ? 'metric-pill' : 'danger-pill'}>
                              {node.is_online ? 'online' : 'offline'}
                            </span>
                            <span className={getNodeRoleTone(node.role)}>{getNodeRoleLabel(node.role)}</span>
                          </div>
                          <p className="mt-2 flex flex-wrap items-center gap-3 text-sm muted">
                            <span className="flex items-center gap-2">
                              <MapPin className="h-4 w-4" />
                              {node.location}
                            </span>
                            <span className="flex items-center gap-2">
                              <Globe2 className="h-4 w-4" />
                              {node.country_code}
                            </span>
                          </p>
                        </div>
                      </div>

                      <div className="flex gap-2">
                        <button onClick={() => openNodeEdit(node)} className="btn-secondary px-3 py-2">
                          <Edit className="h-4 w-4" />
                        </button>
                        <button onClick={() => handleDeleteNode(node)} className="btn-danger px-3 py-2">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>

                    <div className="mt-5 panel-soft px-4 py-3 text-sm">
                      <p className="muted">Endpoint</p>
                      <p className="mt-1 font-semibold break-all">{node.endpoint}:{node.port}</p>
                    </div>

                    <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                      <div className="panel-soft px-4 py-4">
                        <p className="text-xs uppercase tracking-[0.18em] muted">Клиенты</p>
                        <p className="mt-2 flex items-center gap-2 text-lg font-bold">
                          <Users className="h-4 w-4 text-cyan-200" />
                          {node.current_clients} / {node.max_clients}
                        </p>
                      </div>
                      <div className="panel-soft px-4 py-4">
                        <p className="text-xs uppercase tracking-[0.18em] muted">Нагрузка</p>
                        <p className="mt-2">
                          <span className={getLoadTone(node.load_percent)}>
                            {(node.load_percent || 0).toFixed(1)}%
                          </span>
                        </p>
                      </div>
                      <div className="panel-soft px-4 py-4">
                        <p className="text-xs uppercase tracking-[0.18em] muted">Роль в цепочке</p>
                        <p className="mt-2 text-lg font-bold">
                          {node.is_entry_node && node.is_exit_node
                            ? 'Combined node'
                            : node.is_entry_node
                              ? 'Client entry'
                              : 'Internet exit'}
                        </p>
                      </div>
                    </div>

                    <div className="mt-5">
                      <div className="mb-2 flex items-center justify-between text-sm">
                        <span className="muted">Использование ноды</span>
                        <span>{(node.load_percent || 0).toFixed(1)}%</span>
                      </div>
                      <div className="progress-track">
                        <div className="progress-fill" style={{ width: `${Math.min(100, node.load_percent || 0)}%` }} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="space-y-4">
            <div className="flex items-end justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold">Маршруты</h2>
                <p className="mt-1 text-sm muted">
                  Логические цепочки, по которым пользователю выдаётся маршрут, а не просто один сервер.
                </p>
              </div>
              <button onClick={openRouteCreate} className="btn-primary">
                <Plus className="h-5 w-5" />
                Новый route
              </button>
            </div>

            {routeItems.length === 0 ? (
              <div className="empty-state">
                <ArrowRightLeft className="h-10 w-10 text-cyan-200" />
                <div>
                  <p className="text-lg font-semibold">Маршруты ещё не созданы</p>
                  <p className="mt-1 text-sm muted">После route bootstrap здесь появится связка вроде RU -&gt; DE.</p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {routeItems.map((route: any) => (
                  <div key={route.id} className="panel p-6">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-3">
                          <h3 className="text-xl font-bold">{route.name}</h3>
                          <span className={route.is_active ? 'metric-pill' : 'danger-pill'}>
                            {route.is_active ? 'active' : 'inactive'}
                          </span>
                          <span className={getTunnelTone(route.tunnel_status)}>
                            {getTunnelLabel(route.tunnel_status)}
                          </span>
                          {route.is_default ? (
                            <span className="warning-pill">
                              <ShieldCheck className="h-3.5 w-3.5" />
                              default
                            </span>
                          ) : null}
                        </div>

                        <div className="mt-4 flex flex-col gap-3 text-sm">
                          <div className="panel-soft px-4 py-3">
                            <p className="text-xs uppercase tracking-[0.16em] muted">Entry</p>
                            <p className="mt-2 font-semibold">{route.entry_node_name}</p>
                            <p className="mt-1 muted">{route.entry_node_location}</p>
                          </div>
                          <div className="flex justify-center text-cyan-200/70">
                            <ArrowRightLeft className="h-5 w-5" />
                          </div>
                          <div className="panel-soft px-4 py-3">
                            <p className="text-xs uppercase tracking-[0.16em] muted">Exit</p>
                            <p className="mt-2 font-semibold">{route.exit_node_name || 'Не задан'}</p>
                            <p className="mt-1 muted">{route.exit_node_location || 'Маршрут ещё не замкнут'}</p>
                          </div>
                        </div>
                      </div>

                      <div className="flex gap-2">
                        <button onClick={() => openRouteEdit(route)} className="btn-secondary px-3 py-2">
                          <Edit className="h-4 w-4" />
                        </button>
                        <button onClick={() => handleDeleteRoute(route)} className="btn-danger px-3 py-2">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>

                    <div className="mt-6 grid gap-4 md:grid-cols-3">
                      <div className="panel-soft px-4 py-4">
                        <p className="text-xs uppercase tracking-[0.18em] muted">Клиенты</p>
                        <p className="mt-2 flex items-center gap-2 text-lg font-bold">
                          <Users className="h-4 w-4 text-cyan-200" />
                          {route.current_clients} / {route.max_clients}
                        </p>
                      </div>
                      <div className="panel-soft px-4 py-4">
                        <p className="text-xs uppercase tracking-[0.18em] muted">Нагрузка</p>
                        <p className="mt-2">
                          <span className={getLoadTone(route.load_percent)}>
                            {(route.load_percent || 0).toFixed(1)}%
                          </span>
                        </p>
                      </div>
                      <div className="panel-soft px-4 py-4">
                        <p className="text-xs uppercase tracking-[0.18em] muted">Tunnel</p>
                        <p className="mt-2 text-lg font-bold">
                          {route.tunnel_interface || 'awg0'}
                        </p>
                        <p className="mt-1 text-sm muted">{getTunnelLabel(route.tunnel_status)}</p>
                      </div>
                      <div className="panel-soft px-4 py-4">
                        <p className="text-xs uppercase tracking-[0.18em] muted">Назначение</p>
                        <p className="mt-2 text-lg font-bold">
                          {route.is_default ? 'Основной маршрут' : 'Резерв / доп. маршрут'}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="panel p-6">
            <h2 className="text-2xl font-bold">Legacy compatibility</h2>
            <p className="mt-2 text-sm muted">
              Основной UI больше не зависит от `/admin/servers`. Legacy API сохранён для совместимости и rollback-сценариев.
            </p>
          </section>
        </>
      )}

      {showNodeModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
          <div className="glass w-full max-w-3xl p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold">{editingNode ? 'Редактирование node' : 'Новая node'}</h2>
                <p className="mt-2 text-sm muted">Entry-ноды синхронизируются с legacy `vpn_servers`, чтобы текущая выдача клиентов не ломалась.</p>
              </div>
              <button onClick={() => setShowNodeModal(false)} className="btn-secondary px-3 py-2">
                Закрыть
              </button>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-sm muted">Name</span>
                <input className="input" value={nodeForm.name} onChange={(e) => setNodeForm({ ...nodeForm, name: e.target.value })} />
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Role</span>
                <select className="input" value={nodeForm.role} onChange={(e) => setNodeForm({ ...nodeForm, role: e.target.value })}>
                  <option value="entry">entry</option>
                  <option value="exit">exit</option>
                  <option value="combined">combined</option>
                </select>
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Country code</span>
                <input className="input" maxLength={2} value={nodeForm.country_code} onChange={(e) => setNodeForm({ ...nodeForm, country_code: e.target.value.toUpperCase() })} />
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Location</span>
                <input className="input" value={nodeForm.location} onChange={(e) => setNodeForm({ ...nodeForm, location: e.target.value })} />
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Endpoint</span>
                <input className="input" value={nodeForm.endpoint} onChange={(e) => setNodeForm({ ...nodeForm, endpoint: e.target.value })} />
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Port</span>
                <input className="input" type="number" value={nodeForm.port} onChange={(e) => setNodeForm({ ...nodeForm, port: e.target.value })} />
              </label>
              <label className="space-y-2 md:col-span-2">
                <span className="text-sm muted">Public key</span>
                <textarea className="input min-h-[110px]" value={nodeForm.public_key} onChange={(e) => setNodeForm({ ...nodeForm, public_key: e.target.value })} />
              </label>
              <label className="space-y-2 md:col-span-2">
                <span className="text-sm muted">Private key</span>
                <textarea className="input min-h-[110px]" value={nodeForm.private_key} onChange={(e) => setNodeForm({ ...nodeForm, private_key: e.target.value })} placeholder={editingNode ? 'Оставь пустым, чтобы не менять' : ''} />
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Max clients</span>
                <input className="input" type="number" value={nodeForm.max_clients} onChange={(e) => setNodeForm({ ...nodeForm, max_clients: e.target.value })} />
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="panel-soft flex items-center gap-3 px-4 py-3">
                  <input type="checkbox" checked={nodeForm.is_active} onChange={(e) => setNodeForm({ ...nodeForm, is_active: e.target.checked })} />
                  <span>Active</span>
                </label>
                <label className="panel-soft flex items-center gap-3 px-4 py-3">
                  <input type="checkbox" checked={nodeForm.is_online} onChange={(e) => setNodeForm({ ...nodeForm, is_online: e.target.checked })} />
                  <span>Online</span>
                </label>
              </div>
            </div>

            {nodeError ? (
              <div className="mt-4 rounded-2xl border border-red-300/20 bg-red-300/10 px-4 py-3 text-sm text-red-100">
                {nodeError}
              </div>
            ) : null}

            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setShowNodeModal(false)} className="btn-secondary">Отмена</button>
              <button onClick={submitNode} className="btn-primary">
                {saveNodeMutation.isLoading ? 'Сохраняем...' : editingNode ? 'Обновить node' : 'Создать node'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {showRouteModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
          <div className="glass w-full max-w-2xl p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold">{editingRoute ? 'Редактирование route' : 'Новый route'}</h2>
                <p className="mt-2 text-sm muted">Маршрут связывает клиентский entry-узел с exit-узлом и задаёт default path для новых выдач.</p>
              </div>
              <button onClick={() => setShowRouteModal(false)} className="btn-secondary px-3 py-2">
                Закрыть
              </button>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="space-y-2 md:col-span-2">
                <span className="text-sm muted">Name</span>
                <input className="input" value={routeForm.name} onChange={(e) => setRouteForm({ ...routeForm, name: e.target.value })} />
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Entry node</span>
                <select className="input" value={routeForm.entry_node_id} onChange={(e) => setRouteForm({ ...routeForm, entry_node_id: e.target.value })}>
                  <option value="">Выбери entry node</option>
                  {entryNodes.map((node: any) => (
                    <option key={node.id} value={String(node.id)}>{node.name} · {node.location}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Exit node</span>
                <select className="input" value={routeForm.exit_node_id} onChange={(e) => setRouteForm({ ...routeForm, exit_node_id: e.target.value })}>
                  <option value="">Без exit node</option>
                  {exitNodes.map((node: any) => (
                    <option key={node.id} value={String(node.id)}>{node.name} · {node.location}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Priority</span>
                <input className="input" type="number" value={routeForm.priority} onChange={(e) => setRouteForm({ ...routeForm, priority: e.target.value })} />
              </label>
              <label className="space-y-2">
                <span className="text-sm muted">Max clients</span>
                <input className="input" type="number" placeholder="auto by node capacity" value={routeForm.max_clients} onChange={(e) => setRouteForm({ ...routeForm, max_clients: e.target.value })} />
              </label>
              <div className="grid gap-3 md:col-span-2 sm:grid-cols-2">
                <label className="panel-soft flex items-center gap-3 px-4 py-3">
                  <input type="checkbox" checked={routeForm.is_active} onChange={(e) => setRouteForm({ ...routeForm, is_active: e.target.checked })} />
                  <span>Active route</span>
                </label>
                <label className="panel-soft flex items-center gap-3 px-4 py-3">
                  <input type="checkbox" checked={routeForm.is_default} onChange={(e) => setRouteForm({ ...routeForm, is_default: e.target.checked })} />
                  <span>Default route</span>
                </label>
              </div>
            </div>

            {routeError ? (
              <div className="mt-4 rounded-2xl border border-red-300/20 bg-red-300/10 px-4 py-3 text-sm text-red-100">
                {routeError}
              </div>
            ) : null}

            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setShowRouteModal(false)} className="btn-secondary">Отмена</button>
              <button onClick={submitRoute} className="btn-primary">
                {saveRouteMutation.isLoading ? 'Сохраняем...' : editingRoute ? 'Обновить route' : 'Создать route'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

    </div>
  )
}

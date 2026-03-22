import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from 'react-query'
import { Activity, Edit, MapPin, Plus, Server, Trash2, Users } from 'lucide-react'
import { adminApi } from '../lib/api'

function getLoadTone(load?: number) {
  if ((load || 0) >= 80) return 'danger-pill'
  if ((load || 0) >= 50) return 'warning-pill'
  return 'metric-pill'
}

export default function Servers() {
  const [showModal, setShowModal] = useState(false)
  const [editingServer, setEditingServer] = useState<any>(null)
  const queryClient = useQueryClient()

  const { data: servers, isLoading } = useQuery('admin-servers', () => adminApi.getServers())

  const deleteMutation = useMutation((id: number) => adminApi.deleteServer(id), {
    onSuccess: () => queryClient.invalidateQueries('admin-servers'),
  })

  const serverItems = servers?.data?.servers || []
  const onlineCount = serverItems.filter((server: any) => server.is_online).length

  const handleDelete = async (id: number) => {
    if (confirm('Удалить сервер?')) {
      await deleteMutation.mutateAsync(id)
    }
  }

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <h1 className="page-title">VPN Серверы</h1>
          <p className="page-subtitle">
            {onlineCount} из {serverItems.length} серверов сейчас онлайн.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="panel-soft px-4 py-3 text-sm">
            <p className="muted">Суммарная ёмкость</p>
            <p className="mt-1 font-bold">
              {serverItems.reduce((sum: number, item: any) => sum + (item.max_clients || 0), 0)} клиентов
            </p>
          </div>
          <button
            onClick={() => {
              setEditingServer(null)
              setShowModal(true)
            }}
            className="btn-primary"
          >
            <Plus className="h-5 w-5" />
            Добавить сервер
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="empty-state">
          <Activity className="h-10 w-10 text-cyan-200" />
          <div>
            <p className="text-lg font-semibold">Загружаем список узлов</p>
            <p className="mt-1 text-sm muted">Собираем информацию о доступности и нагрузке серверов.</p>
          </div>
        </div>
      ) : serverItems.length === 0 ? (
        <div className="empty-state">
          <Server className="h-10 w-10 text-cyan-200" />
          <div>
            <p className="text-lg font-semibold">Серверы ещё не добавлены</p>
            <p className="mt-1 text-sm muted">После появления API-формы здесь можно будет управлять узлами.</p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {serverItems.map((server: any) => (
            <div key={server.id} className="panel p-6">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex items-start gap-4">
                  <div
                    className={[
                      'rounded-2xl p-3 ring-1',
                      server.is_online
                        ? 'bg-emerald-300/12 text-emerald-200 ring-emerald-200/10'
                        : 'bg-red-300/12 text-red-200 ring-red-200/10',
                    ].join(' ')}
                  >
                    <Server className="h-6 w-6" />
                  </div>
                  <div>
                    <div className="flex flex-wrap items-center gap-3">
                      <h3 className="text-xl font-bold">{server.name}</h3>
                      <span className={server.is_online ? 'metric-pill' : 'danger-pill'}>
                        {server.is_online ? 'online' : 'offline'}
                      </span>
                    </div>
                    <p className="mt-2 flex items-center gap-2 text-sm muted">
                      <MapPin className="h-4 w-4" />
                      {server.location}
                    </p>
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setEditingServer(server)
                      setShowModal(true)
                    }}
                    className="btn-secondary px-3 py-2"
                  >
                    <Edit className="h-4 w-4" />
                  </button>
                  <button onClick={() => handleDelete(server.id)} className="btn-danger px-3 py-2">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-3">
                <div className="panel-soft px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.18em] muted">Клиенты</p>
                  <p className="mt-2 flex items-center gap-2 text-lg font-bold">
                    <Users className="h-4 w-4 text-cyan-200" />
                    {server.current_clients} / {server.max_clients}
                  </p>
                </div>
                <div className="panel-soft px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.18em] muted">Нагрузка</p>
                  <p className="mt-2">
                    <span className={getLoadTone(server.load_percent)}>
                      {(server.load_percent || 0).toFixed(1)}%
                    </span>
                  </p>
                </div>
                <div className="panel-soft px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.18em] muted">Ёмкость</p>
                  <p className="mt-2 text-lg font-bold">
                    {server.max_clients - server.current_clients > 0
                      ? `${server.max_clients - server.current_clients} свободно`
                      : 'Лимит достигнут'}
                  </p>
                </div>
              </div>

              <div className="mt-5">
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="muted">Использование сервера</span>
                  <span>{(server.load_percent || 0).toFixed(1)}%</span>
                </div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${Math.min(100, server.load_percent || 0)}%` }} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
          <div className="glass w-full max-w-lg p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold">{editingServer ? 'Редактирование сервера' : 'Новый сервер'}</h2>
                <p className="mt-2 text-sm muted">
                  Форма API ещё не реализована полностью, поэтому оставил честную заглушку вместо пустого муляжа.
                </p>
              </div>
              <button onClick={() => setShowModal(false)} className="btn-secondary px-3 py-2">
                Закрыть
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

import axios from 'axios'

const API_BASE = '/api'

export const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('admin_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const adminApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),

  getCurrentUser: () =>
    api.get('/users/me'),
  
  getStats: () =>
    api.get('/admin/stats'),
  
  getRevenueAnalytics: (days: number = 30) =>
    api.get(`/admin/analytics/revenue?days=${days}`),
  
  getUsersAnalytics: (days: number = 30) =>
    api.get(`/admin/analytics/users?days=${days}`),
  
  getUsers: (page = 1, search = '') =>
    api.get(`/admin/users?page=${page}&search=${search}`),
  
  getUser: (id: number) =>
    api.get(`/admin/users/${id}`),
  
  updateUser: (id: number, data: any) =>
    api.put(`/admin/users/${id}`, data),
  
  getServers: () =>
    api.get('/admin/servers'),

  getNodes: () =>
    api.get('/admin/nodes'),

  createNode: (data: any) =>
    api.post('/admin/nodes', data),

  updateNode: (id: number, data: any) =>
    api.put(`/admin/nodes/${id}`, data),

  deleteNode: (id: number) =>
    api.delete(`/admin/nodes/${id}`),

  getRoutes: () =>
    api.get('/admin/routes'),

  createRoute: (data: any) =>
    api.post('/admin/routes', data),

  updateRoute: (id: number, data: any) =>
    api.put(`/admin/routes/${id}`, data),

  deleteRoute: (id: number) =>
    api.delete(`/admin/routes/${id}`),
  
  createServer: (data: any) =>
    api.post('/admin/servers', data),
  
  updateServer: (id: number, data: any) =>
    api.put(`/admin/servers/${id}`, data),
  
  deleteServer: (id: number) =>
    api.delete(`/admin/servers/${id}`),
  
  getPlans: () =>
    api.get('/admin/billing/plans'),
  
  createPlan: (data: any) =>
    api.post('/admin/billing/plans', data),
  
  updatePlan: (id: number, data: any) =>
    api.put(`/admin/billing/plans/${id}`, data),
  
  deletePlan: (id: number) =>
    api.delete(`/admin/billing/plans/${id}`),
  
  getBillingStats: () =>
    api.get('/admin/billing/stats'),
  
  getReferralStats: () =>
    api.get('/admin/referrals/stats'),
  
  getSystemHealth: () =>
    api.get('/admin/system/health'),
}

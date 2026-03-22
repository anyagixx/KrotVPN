import axios from 'axios'

const API_BASE = '/api'

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor - add auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor - handle auth errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      
      // Try to refresh token
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${API_BASE}/auth/refresh`, {
            refresh_token: refreshToken,
          })
          
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`
          return api(originalRequest)
        } catch {
          // Refresh failed, clear tokens
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      } else {
        window.location.href = '/login'
      }
    }
    
    return Promise.reject(error)
  }
)

// Types
export interface User {
  id: number
  email: string | null
  telegram_id: number | null
  telegram_username: string | null
  name: string | null
  display_name: string
  language: string
  role: string
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface VPNConfig {
  config: string
  server_name: string
  server_location: string
  address: string
  created_at: string
}

export interface VPNStats {
  total_upload_bytes: number
  total_download_bytes: number
  total_upload_formatted: string
  total_download_formatted: string
  last_handshake_at: string | null
  is_connected: boolean
  server_name: string
  server_location: string
}

export interface UserStats {
  total_upload_bytes: number
  total_download_bytes: number
  subscription_days_left: number
  has_active_subscription: boolean
  referrals_count: number
  referral_bonus_days: number
}

export interface Plan {
  id: number
  name: string
  price: number
  duration_days: number
  features: string[]
  is_active: boolean
}

export interface SubscriptionStatus {
  has_subscription: boolean
  is_active: boolean
  is_trial: boolean
  plan_name: string | null
  days_left: number
  expires_at: string | null
  is_recurring: boolean
}

export interface ReferralStats {
  total_referrals: number
  bonus_days_earned: number
  paid_referrals?: number
}

export interface ReferralListItem {
  id: number
  bonus_given: boolean
  bonus_days: number
  created_at: string
  first_payment_at: string | null
}

// Auth API
export const authApi = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }),
  
  register: (email: string, password: string, referral_code?: string) =>
    api.post<TokenResponse>('/auth/register', { email, password, referral_code }),
  
  telegramAuth: (telegram_id: number, telegram_username?: string, referral_code?: string) =>
    api.post<TokenResponse>('/auth/telegram', { telegram_id, telegram_username, referral_code }),
  
  refresh: (refresh_token: string) =>
    api.post<TokenResponse>('/auth/refresh', { refresh_token }),
}

// User API
export const userApi = {
  getMe: () =>
    api.get<User>('/users/me'),
  
  getStats: () =>
    api.get<UserStats>('/users/me/stats'),
  
  updateProfile: (data: { name?: string; language?: string }) =>
    api.put<User>('/users/me', data),
  
  changePassword: (current_password: string, new_password: string) =>
    api.post('/users/me/change-password', { current_password, new_password }),
}

// VPN API
export const vpnApi = {
  getConfig: () =>
    api.get<VPNConfig>('/vpn/config'),
  
  downloadConfig: () =>
    api.get('/vpn/config/download', { responseType: 'blob' }),
  
  getQRCode: () =>
    api.get('/vpn/config/qr', { responseType: 'blob' }),
  
  getStats: () =>
    api.get<VPNStats>('/vpn/stats'),
  
  getServers: () =>
    api.get('/vpn/servers'),
}

// Billing API
export const billingApi = {
  getPlans: () =>
    api.get<Plan[]>('/billing/plans'),
  
  getSubscription: () =>
    api.get<SubscriptionStatus>('/billing/subscription'),
  
  createPayment: (plan_id: number) =>
    api.post('/billing/subscribe', { plan_id }),
}

// Referral API
export const referralApi = {
  getCode: () =>
    api.get('/referrals/code'),
  
  getStats: () =>
    api.get<ReferralStats>('/referrals/stats'),

  getList: () =>
    api.get<{ items: ReferralListItem[]; total: number }>('/referrals/list'),
}

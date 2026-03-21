import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Mail, Lock, Loader2, Shield } from 'lucide-react'
import toast from 'react-hot-toast'
import { authApi } from '../lib/api'

export default function Login() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    
    try {
      const { data } = await authApi.login(email, password)
      
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      
      // Fetch user data
      await authApi.refresh(data.refresh_token)
      
      toast.success(t('success'))
      navigate('/')
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('invalidCredentials'))
    } finally {
      setLoading(false)
    }
  }
  
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="glass-card">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 mx-auto rounded-2xl gradient-bg flex items-center justify-center mb-4 shadow-lg shadow-primary-500/25">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-bold">{t('loginTitle')}</h1>
            <p className="text-dark-400 mt-2">{t('appName')}</p>
          </div>
          
          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="input-group">
              <Mail className="icon w-5 h-5" />
              <input
                type="email"
                className="input"
                placeholder={t('email')}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            
            <div className="input-group">
              <Lock className="icon w-5 h-5" />
              <input
                type="password"
                className="input"
                placeholder={t('password')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            
            <button
              type="submit"
              className="btn-primary w-full py-3"
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                t('loginButton')
              )}
            </button>
          </form>
          
          {/* Footer */}
          <div className="mt-6 text-center text-dark-400">
            <p>
              {t('noAccount')}{' '}
              <Link to="/register" className="text-primary-400 hover:text-primary-300">
                {t('register')}
              </Link>
            </p>
          </div>
          
          {/* Telegram Login */}
          <div className="mt-6 pt-6 border-t border-dark-700">
            <p className="text-center text-dark-400 text-sm mb-4">
              Или войдите через Telegram
            </p>
            <button className="btn-secondary w-full py-3">
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.161c-.18 1.897-.962 6.502-1.359 8.627-.168.9-.5 1.201-.82 1.23-.697.064-1.226-.461-1.901-.903-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.015-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.139-5.062 3.345-.479.329-.913.489-1.302.481-.428-.009-1.252-.242-1.865-.442-.751-.244-1.349-.374-1.297-.789.027-.216.324-.437.893-.663 3.498-1.524 5.831-2.529 6.998-3.015 3.333-1.386 4.025-1.627 4.477-1.635.099-.002.321.023.465.141.121.1.154.234.17.331.015.098.034.322.019.496z"/>
              </svg>
              Telegram
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

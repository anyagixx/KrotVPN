import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Mail, Lock, Loader2, Shield } from 'lucide-react'
import toast from 'react-hot-toast'
import { authApi } from '../lib/api'

export default function Register() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  
  const referralCode = searchParams.get('ref')
  
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (password !== confirmPassword) {
      toast.error('Passwords do not match')
      return
    }
    
    setLoading(true)
    
    try {
      const { data } = await authApi.register(email, password, referralCode || undefined)
      
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      
      toast.success(t('registrationSuccess'))
      navigate('/')
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('error'))
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
            <h1 className="text-2xl font-bold">{t('registerTitle')}</h1>
            <p className="text-dark-400 mt-2">
              {t('trialDays', { days: 3 })}
            </p>
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
                minLength={8}
              />
            </div>
            
            <div className="input-group">
              <Lock className="icon w-5 h-5" />
              <input
                type="password"
                className="input"
                placeholder={t('confirmPassword')}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>
            
            {referralCode && (
              <div className="text-sm text-dark-400">
                Реферальный код: <span className="text-primary-400">{referralCode}</span>
              </div>
            )}
            
            <button
              type="submit"
              className="btn-primary w-full py-3"
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                t('registerButton')
              )}
            </button>
          </form>
          
          {/* Footer */}
          <div className="mt-6 text-center text-dark-400">
            <p>
              {t('hasAccount')}{' '}
              <Link to="/login" className="text-primary-400 hover:text-primary-300">
                {t('login')}
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

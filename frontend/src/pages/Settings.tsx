import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from 'react-query'
import { User, Globe, Lock, Save } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuthStore } from '../stores/auth'
import { userApi } from '../lib/api'

export default function Settings() {
  const { t, i18n } = useTranslation()
  const { user, setUser } = useAuthStore()
  
  const [name, setName] = useState(user?.name || '')
  const [language, setLanguage] = useState(user?.language || 'ru')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  
  const updateProfile = useMutation(
    (data: { name?: string; language?: string }) => userApi.updateProfile(data),
    {
      onSuccess: (response: any) => {
        setUser(response.data)
        i18n.changeLanguage(response.data.language)
        localStorage.setItem('language', response.data.language)
        toast.success(t('success'))
      },
      onError: () => toast.error(t('error')),
    }
  )
  
  const changePassword = useMutation(
    () => userApi.changePassword(currentPassword, newPassword),
    {
      onSuccess: () => {
        setCurrentPassword('')
        setNewPassword('')
        toast.success(t('passwordChanged'))
      },
      onError: () => toast.error(t('error')),
    }
  )
  
  const handleSaveProfile = () => {
    updateProfile.mutate({ name, language })
  }
  
  const handleChangePassword = (e: React.FormEvent) => {
    e.preventDefault()
    if (newPassword.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    changePassword.mutate()
  }
  
  return (
    <div className="space-y-8 animate-in max-w-2xl">
      <div>
        <h1 className="text-3xl font-bold">{t('settings')}</h1>
        <p className="text-dark-400 mt-2">
          Управление аккаунтом и настройками
        </p>
      </div>
      
      {/* Profile */}
      <div className="glass-card">
        <div className="flex items-center gap-3 mb-6">
          <User className="w-5 h-5 text-dark-400" />
          <h3 className="font-semibold">{t('profile')}</h3>
        </div>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-dark-400 mb-2">
              {t('email')}
            </label>
            <input
              type="email"
              value={user?.email || ''}
              disabled
              className="input opacity-50"
            />
          </div>
          
          <div>
            <label className="block text-sm text-dark-400 mb-2">
              Имя
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input"
              placeholder="Ваше имя"
            />
          </div>
          
          <button
            onClick={handleSaveProfile}
            disabled={updateProfile.isLoading}
            className="btn-primary"
          >
            <Save className="w-5 h-5" />
            {t('save')}
          </button>
        </div>
      </div>
      
      {/* Language */}
      <div className="glass-card">
        <div className="flex items-center gap-3 mb-6">
          <Globe className="w-5 h-5 text-dark-400" />
          <h3 className="font-semibold">{t('language')}</h3>
        </div>
        
        <div className="flex gap-4">
          <button
            onClick={() => {
              setLanguage('ru')
              updateProfile.mutate({ language: 'ru' })
            }}
            className={`flex-1 py-3 rounded-xl border transition-all ${
              language === 'ru'
                ? 'border-primary-500 bg-primary-500/10 text-primary-400'
                : 'border-dark-600 hover:border-dark-500'
            }`}
          >
            🇷🇺 Русский
          </button>
          <button
            onClick={() => {
              setLanguage('en')
              updateProfile.mutate({ language: 'en' })
            }}
            className={`flex-1 py-3 rounded-xl border transition-all ${
              language === 'en'
                ? 'border-primary-500 bg-primary-500/10 text-primary-400'
                : 'border-dark-600 hover:border-dark-500'
            }`}
          >
            🇬🇧 English
          </button>
        </div>
      </div>
      
      {/* Change Password */}
      <div className="glass-card">
        <div className="flex items-center gap-3 mb-6">
          <Lock className="w-5 h-5 text-dark-400" />
          <h3 className="font-semibold">{t('changePassword')}</h3>
        </div>
        
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label className="block text-sm text-dark-400 mb-2">
              {t('currentPassword')}
            </label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="input"
              required
            />
          </div>
          
          <div>
            <label className="block text-sm text-dark-400 mb-2">
              {t('newPassword')}
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="input"
              required
              minLength={8}
            />
          </div>
          
          <button
            type="submit"
            disabled={changePassword.isLoading}
            className="btn-secondary"
          >
            <Lock className="w-5 h-5" />
            {t('changePassword')}
          </button>
        </form>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Eye, EyeOff, CheckCircle, AlertCircle, X } from 'lucide-react'
import APIClient from '../../api/client'

export function WifiModal({ robotId, onClose }) {
  const [ssid, setSsid] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [state, setState] = useState('idle') // 'idle' | 'success' | 'error'
  const [errorMessage, setErrorMessage] = useState('')

  const handleSubmit = async () => {
    if (!ssid.trim() || !password.trim()) {
      setErrorMessage('SSID and password are required')
      setState('error')
      return
    }

    try {
      setIsLoading(true)
      setState('idle')
      setErrorMessage('')
      await APIClient.sendWifiCredentials(robotId, ssid, password)
      setState('success')
      setTimeout(() => {
        onClose()
      }, 2000)
    } catch (err) {
      setErrorMessage(err.message || 'Failed to send WiFi credentials')
      setState('error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface border border-border rounded-card p-6 max-w-md w-full mx-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Send WiFi Credentials</h2>
          <button
            onClick={onClose}
            className="text-text-secondary hover:text-text-primary transition"
          >
            <X size={20} />
          </button>
        </div>

        {state === 'success' && (
          <div className="mb-4 p-3 bg-accent/10 border border-accent rounded-card flex items-center gap-2 text-accent">
            <CheckCircle size={20} />
            <span className="text-sm">Credentials sent successfully!</span>
          </div>
        )}

        {state === 'error' && (
          <div className="mb-4 p-3 bg-danger/10 border border-danger rounded-card flex items-center gap-2 text-danger">
            <AlertCircle size={20} />
            <span className="text-sm">{errorMessage}</span>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              SSID
            </label>
            <input
              type="text"
              value={ssid}
              onChange={(e) => setSsid(e.target.value)}
              placeholder="Network name"
              disabled={isLoading || state === 'success'}
              className="w-full px-3 py-2 bg-background border border-border rounded-button text-text-primary placeholder-text-secondary focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 disabled:opacity-50 transition"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Network password"
                disabled={isLoading || state === 'success'}
                className="w-full px-3 py-2 bg-background border border-border rounded-button text-text-primary placeholder-text-secondary focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 disabled:opacity-50 transition"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary transition"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={onClose}
              disabled={isLoading}
              className="flex-1 px-4 py-2 bg-background border border-border text-text-primary font-medium rounded-button hover:bg-[#1a1a1a] disabled:opacity-50 transition"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={isLoading || state === 'success'}
              className="flex-1 px-4 py-2 bg-accent text-background font-medium rounded-button hover:opacity-90 disabled:opacity-50 transition"
            >
              {isLoading ? 'Sending...' : 'Send'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default WifiModal

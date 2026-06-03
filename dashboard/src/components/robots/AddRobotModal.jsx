import { useState } from 'react'
import { X, CheckCircle, AlertCircle } from 'lucide-react'
import APIClient from '../../api/client'
import { useRobotsContext } from '../../context/RobotsContext'

export function AddRobotModal({ onClose }) {
  const { selectRobot } = useRobotsContext()
  const [robotId, setRobotId] = useState('')
  const [name, setName] = useState('')
  const [ipAddress, setIpAddress] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [state, setState] = useState('idle') // 'idle' | 'success' | 'error'
  const [errorMessage, setErrorMessage] = useState('')

  const handleSubmit = async () => {
    if (!robotId.trim() || !name.trim() || !ipAddress.trim()) {
      setErrorMessage('All fields are required')
      setState('error')
      return
    }

    try {
      setIsLoading(true)
      setState('idle')
      setErrorMessage('')
      await APIClient.registerRobot(robotId, name, ipAddress)
      setState('success')
      setTimeout(() => {
        selectRobot(robotId)
        onClose()
      }, 1500)
    } catch (err) {
      setErrorMessage(err.message || 'Failed to register robot')
      setState('error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface border border-border rounded-card p-6 max-w-md w-full mx-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Add Robot</h2>
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
            <span className="text-sm">Robot registered successfully!</span>
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
              Robot ID
            </label>
            <input
              type="text"
              value={robotId}
              onChange={(e) => setRobotId(e.target.value)}
              placeholder="e.g., robot-01"
              disabled={isLoading || state === 'success'}
              className="w-full px-3 py-2 bg-background border border-border rounded-button text-text-primary placeholder-text-secondary focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 disabled:opacity-50 transition"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              Robot Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Garden Monitor"
              disabled={isLoading || state === 'success'}
              className="w-full px-3 py-2 bg-background border border-border rounded-button text-text-primary placeholder-text-secondary focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 disabled:opacity-50 transition"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              IP Address
            </label>
            <input
              type="text"
              value={ipAddress}
              onChange={(e) => setIpAddress(e.target.value)}
              placeholder="e.g., 192.168.1.100"
              disabled={isLoading || state === 'success'}
              className="w-full px-3 py-2 bg-background border border-border rounded-button text-text-primary placeholder-text-secondary focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 disabled:opacity-50 transition"
            />
          </div>

          <div className="flex gap-2 pt-2">
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
              {isLoading ? 'Adding...' : 'Add Robot'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AddRobotModal

/**
 * Reusable WebSocket manager with auto-reconnect and exponential backoff.
 */
export class RobotWebSocket {
  constructor(url, { onMessage, onStatusChange, maxRetries = 5 } = {}) {
    this.url = url
    this.onMessage = onMessage || (() => {})
    this.onStatusChange = onStatusChange || (() => {})
    this.maxRetries = maxRetries
    this.retryCount = 0
    this.ws = null
    this.status = 'disconnected'
    this.messageQueue = []
    this.reconnectTimer = null
  }

  connect() {
    if (this.status === 'connecting' || this.status === 'connected') {
      return
    }

    this._setStatus('connecting')

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        this._setStatus('connected')
        this.retryCount = 0
        this._flushMessageQueue()
      }

      this.ws.onmessage = (event) => {
        this.onMessage(event)
      }

      this.ws.onerror = (error) => {
        console.error(`WebSocket error on ${this.url}:`, error)
      }

      this.ws.onclose = () => {
        this._setStatus('disconnected')
        this._scheduleReconnect()
      }
    } catch (error) {
      console.error(`Failed to create WebSocket for ${this.url}:`, error)
      this._setStatus('disconnected')
      this._scheduleReconnect()
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }

    this._setStatus('disconnected')
  }

  send(data) {
    if (this.status === 'connected' && this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = typeof data === 'string' ? data : JSON.stringify(data)
      this.ws.send(message)
    } else {
      this.messageQueue.push(data)
    }
  }

  sendBinary(data) {
    if (this.status === 'connected' && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(data)
    }
  }

  _setStatus(newStatus) {
    if (this.status !== newStatus) {
      this.status = newStatus
      this.onStatusChange(newStatus)
    }
  }

  _scheduleReconnect() {
    if (this.retryCount >= this.maxRetries) {
      console.warn(`Max reconnection attempts (${this.maxRetries}) reached for ${this.url}`)
      return
    }

    const delay = Math.min(500 * Math.pow(2, this.retryCount), 10000)
    this.retryCount += 1

    this.reconnectTimer = setTimeout(() => {
      console.log(`Reconnecting to ${this.url} (attempt ${this.retryCount}/${this.maxRetries})...`)
      this.connect()
    }, delay)
  }

  _flushMessageQueue() {
    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift()
      this.send(message)
    }
  }

  isConnected() {
    return this.status === 'connected'
  }

  getStatus() {
    return this.status
  }
}

export default RobotWebSocket

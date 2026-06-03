const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000'

export class APIClient {
  static async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    }

    // TODO: Add authentication token header here when implemented
    // headers['Authorization'] = `Bearer ${token}`

    const response = await fetch(url, {
      ...options,
      headers,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }

    return response.json()
  }

  static async get(endpoint) {
    return this.request(endpoint, { method: 'GET' })
  }

  static async post(endpoint, body) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  static async getHealth() {
    return this.get('/health')
  }

  static async getRobots() {
    return this.get('/api/robots')
  }

  static async getRobot(robotId) {
    return this.get(`/api/robots/${robotId}`)
  }

  static async registerRobot(robotId, name, ipAddress) {
    return this.post('/api/robots/register', { robot_id: robotId, name, ip_address: ipAddress })
  }

  static async sendCommand(robotId, command) {
    return this.post(`/api/robots/${robotId}/command`, { command })
  }

  static async sendWifiCredentials(robotId, ssid, password) {
    return this.post(`/api/robots/${robotId}/wifi`, { ssid, password })
  }

  static async getModels() {
    return this.get('/api/models')
  }

  static async getModel(modelName) {
    return this.get(`/api/models/${modelName}`)
  }
}

export default APIClient

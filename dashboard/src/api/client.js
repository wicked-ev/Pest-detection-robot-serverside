// Empty by default: requests stay same-origin and the Vite dev proxy forwards them to the server.
const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// Builds "?a=1&b=2", skipping empty values.
function queryString(params) {
  const entries = Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== "");
  return entries.length ? `?${new URLSearchParams(entries)}` : "";
}

export class APIClient {
  static async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    // TODO: Add authentication token header here when implemented
    // headers['Authorization'] = `Bearer ${token}`

    const response = await fetch(url, {
      ...options,
      cache: "no-store",
      headers,
    });

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  static async get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: "GET" });
  }

  static async post(endpoint, body, options = {}) {
    return this.request(endpoint, {
      ...options,
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  static async getHealth() {
    return this.get("/health");
  }

  static async getRobots(options = {}) {
    return this.get("/api/robots", options);
  }

  static async getRobot(robotId) {
    return this.get(`/api/robots/${robotId}`);
  }

  static async registerRobot(robotId, name, ipAddress) {
    return this.post("/api/robots/register", {
      robot_id: robotId,
      name,
      ip_address: ipAddress,
    });
  }

  static async deleteRobot(robotId) {
    return this.request(`/api/robots/${encodeURIComponent(robotId)}`, { method: "DELETE" });
  }

  static async getSightings(filters = {}) {
    return this.get(`/api/sightings${queryString(filters)}`);
  }

  static async getSightingSummary(filters = {}) {
    return this.get(`/api/sightings/summary${queryString(filters)}`);
  }

  // extra: e.g. { direction, speed } for "move", { duration } for "spray", { enabled } for "set_auto_spray"
  static async sendCommand(robotId, command, extra = {}) {
    return this.post(`/api/robots/${robotId}/command`, { command, ...extra });
  }

  static async getSprays(filters = {}) {
    return this.get(`/api/sprays${queryString(filters)}`);
  }

  static async getModels() {
    return this.get("/api/models");
  }

  static async getModel(modelName) {
    return this.get(`/api/models/${modelName}`);
  }
}

export default APIClient;

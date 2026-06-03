export function RobotStatusBadge({ status }) {
  const statusConfig = {
    online: { bg: 'bg-accent', text: 'text-background' },
    provisioning: { bg: 'bg-warning', text: 'text-background' },
    offline: { bg: 'bg-text-secondary', text: 'text-background' },
  }

  const config = statusConfig[status] || statusConfig.offline
  const displayStatus = status.charAt(0).toUpperCase() + status.slice(1)

  return (
    <span className={`${config.bg} ${config.text} text-xs font-medium px-2 py-1 rounded-button whitespace-nowrap`}>
      {displayStatus}
    </span>
  )
}

export default RobotStatusBadge

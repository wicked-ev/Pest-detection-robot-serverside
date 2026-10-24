// The bordered box used for every section of the dashboard.
export function Panel({ title, action, children, className = '' }) {
  return (
    <section className={`bg-surface border border-border rounded-card p-4 ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          {title && <h3 className="font-medium">{title}</h3>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export default Panel

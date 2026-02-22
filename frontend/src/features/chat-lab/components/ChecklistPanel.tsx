import type { ChecklistItem } from '../../../types'

type ChecklistPanelProps = {
  items: ChecklistItem[]
  state: 'idle' | 'loading' | 'error'
}

export function ChecklistPanel({ items, state }: ChecklistPanelProps) {
  return (
    <section className="checklist-panel" aria-live="polite">
      <div className="checklist-header">
        <h3>Agent Checklist</h3>
        <span>{items.length} tasks</span>
      </div>

      {state === 'loading' && <p className="empty">Refreshing checklist...</p>}
      {state === 'error' && <p className="error-text">Unable to load checklist state.</p>}
      {state === 'idle' && items.length === 0 && <p className="empty">No active checklist items for this thread.</p>}

      {items.length > 0 && (
        <ul className="checklist-list">
          {items.map((item) => (
            <li key={`${item.index}-${item.text}`} data-done={item.done ? 'true' : 'false'}>
              <span className="check-icon" aria-hidden="true">
                {item.done ? '✓' : '○'}
              </span>
              <span>{item.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

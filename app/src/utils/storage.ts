/**
 * Type-safe localStorage wrapper
 */

export function getItem<T>(key: string, defaultValue: T): T {
  if (typeof window === 'undefined') return defaultValue

  try {
    const item = localStorage.getItem(key)
    return item ? JSON.parse(item) : defaultValue
  } catch {
    return defaultValue
  }
}

export function setItem<T>(key: string, value: T): void {
  if (typeof window === 'undefined') return

  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch (error) {
    console.error('Failed to save to localStorage:', error)
  }
}

export function removeItem(key: string): void {
  if (typeof window === 'undefined') return

  try {
    localStorage.removeItem(key)
  } catch (error) {
    console.error('Failed to remove from localStorage:', error)
  }
}

/**
 * Clear all Butler-related storage
 */
export function clearAll(): void {
  if (typeof window === 'undefined') return

  const butlerKeys = ['butler-auth', 'butler-settings']
  butlerKeys.forEach(key => {
    try {
      localStorage.removeItem(key)
    } catch (error) {
      console.error(`Failed to remove ${key}:`, error)
    }
  })
}

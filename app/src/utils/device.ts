/**
 * Check if the current device is mobile
 */
export function isMobile(): boolean {
  if (typeof window === 'undefined') return false

  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
    navigator.userAgent
  )
}

/**
 * Check if the app is running as a PWA (installed)
 */
export function isPWA(): boolean {
  if (typeof window === 'undefined') return false

  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    // @ts-expect-error - iOS Safari specific
    window.navigator.standalone === true
  )
}

/**
 * Check if the device supports touch
 */
export function isTouchDevice(): boolean {
  if (typeof window === 'undefined') return false

  return 'ontouchstart' in window || navigator.maxTouchPoints > 0
}

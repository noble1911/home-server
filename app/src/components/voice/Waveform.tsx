import { useEffect, useState } from 'react'

interface WaveformProps {
  isActive: boolean
  levels?: number[]
}

export default function Waveform({ isActive, levels: externalLevels }: WaveformProps) {
  const [internalLevels, setInternalLevels] = useState<number[]>(Array(20).fill(0.3))

  useEffect(() => {
    if (externalLevels) return

    if (!isActive) {
      setInternalLevels(Array(20).fill(0.3))
      return
    }

    const interval = setInterval(() => {
      setInternalLevels(prev => prev.map(() => 0.2 + Math.random() * 0.8))
    }, 50)

    return () => clearInterval(interval)
  }, [isActive, externalLevels])

  const displayLevels = externalLevels || internalLevels

  return (
    <div className="flex items-center justify-center gap-1 h-12 px-4">
      {displayLevels.map((level, i) => (
        <div
          key={i}
          className="w-1 bg-accent rounded-full transition-all duration-75"
          style={{
            height: `${level * 100}%`,
            opacity: isActive ? 1 : 0.3,
          }}
        />
      ))}
    </div>
  )
}

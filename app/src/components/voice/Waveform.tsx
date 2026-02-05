import { useEffect, useState } from 'react'

interface WaveformProps {
  isActive: boolean
}

export default function Waveform({ isActive }: WaveformProps) {
  const [levels, setLevels] = useState<number[]>(Array(20).fill(0.3))

  useEffect(() => {
    if (!isActive) {
      setLevels(Array(20).fill(0.3))
      return
    }

    // Simulate audio levels - in production this would use actual audio data
    const interval = setInterval(() => {
      setLevels(prev => prev.map(() => 0.2 + Math.random() * 0.8))
    }, 50)

    return () => clearInterval(interval)
  }, [isActive])

  return (
    <div className="flex items-center justify-center gap-1 h-12 px-4">
      {levels.map((level, i) => (
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

import { useCallback, useEffect, useRef, useState } from 'react'
import { Room, RoomEvent, ConnectionState, Track } from 'livekit-client'
import type { RemoteTrack, RemoteTrackPublication, RemoteParticipant } from 'livekit-client'
import { useConversationStore } from '../stores/conversationStore'
import { useSettingsStore } from '../stores/settingsStore'
import { getLiveKitToken } from '../services/api'
import type { LiveKitDataMessage } from '../types/conversation'

/** Data topic the voice agent listens on for controls such as interrupt. */
const CONTROL_TOPIC = 'butler-control'

function getLiveKitUrl(): string {
  if (import.meta.env.VITE_LIVEKIT_URL) return import.meta.env.VITE_LIVEKIT_URL
  // Route through the same origin via nginx /livekit/ proxy
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const port = window.location.port ? `:${window.location.port}` : ''
  return `${proto}//${window.location.hostname}${port}/livekit/`
}
const LIVEKIT_URL = getLiveKitUrl()
const BARS = 20
const IDLE_TIMEOUT_MS = 10_000
const DEMO_PROCESSING_MS = 1500

interface UseLiveKitVoiceReturn {
  startListening: () => Promise<void>
  stopListening: () => void
  disconnect: () => void
  /** Stop Butler talking now (the agent drops the rest of its reply). */
  stopSpeaking: () => void
  audioLevels: number[]
  connectionError: string | null
  isLiveKitConnected: boolean
}

export function useLiveKitVoice(): UseLiveKitVoiceReturn {
  const { setRecording, setVoiceStatus, setConnectionStatus, addMessage } =
    useConversationStore()
  const { audioInputDevice, speakReplies } = useSettingsStore()

  const [audioLevels, setAudioLevels] = useState<number[]>(() => Array(BARS).fill(0))
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [isLiveKitConnected, setIsLiveKitConnected] = useState(false)

  // Refs for mutable resources (no re-renders)
  const roomRef = useRef<Room | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animFrameRef = useRef<number>(0)
  const isConnectingRef = useRef(false)
  const demoStreamRef = useRef<MediaStream | null>(null)
  const idleTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const demoTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const agentAudioElRef = useRef<HTMLAudioElement | null>(null)
  const speakRepliesRef = useRef(speakReplies)

  // --- Audio analysis ---

  const connectAnalyserToTrack = useCallback((mediaStreamTrack: MediaStreamTrack) => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext()
    }
    const ctx = audioContextRef.current
    if (ctx.state === 'suspended') {
      ctx.resume()
    }
    const source = ctx.createMediaStreamSource(new MediaStream([mediaStreamTrack]))
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 64
    source.connect(analyser)
    analyserRef.current = analyser
  }, [])

  const startAudioLevelMonitoring = useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser) return

    const dataArray = new Uint8Array(analyser.frequencyBinCount)
    const binSize = Math.max(1, Math.floor(dataArray.length / BARS))

    const update = () => {
      analyser.getByteFrequencyData(dataArray)
      const levels: number[] = []
      for (let i = 0; i < BARS; i++) {
        let sum = 0
        for (let j = 0; j < binSize; j++) {
          const idx = i * binSize + j
          sum += idx < dataArray.length ? dataArray[idx] : 0
        }
        levels.push(sum / binSize / 255)
      }
      setAudioLevels(levels)
      animFrameRef.current = requestAnimationFrame(update)
    }
    update()
  }, [])

  const stopAudioLevelMonitoring = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = 0
    }
    setAudioLevels(Array(BARS).fill(0))
  }, [])

  // --- Data message handling ---

  const handleDataMessage = useCallback((message: LiveKitDataMessage) => {
    switch (message.type) {
      case 'user_transcript':
        if (message.isFinal) {
          addMessage({
            id: crypto.randomUUID(),
            role: 'user',
            content: message.text,
            type: 'voice',
            timestamp: new Date().toISOString(),
          })
        }
        break
      case 'assistant_transcript':
        if (message.isFinal) {
          addMessage({
            id: crypto.randomUUID(),
            role: 'assistant',
            content: message.text,
            type: 'voice',
            timestamp: new Date().toISOString(),
          })
        }
        break
      case 'visual_content':
        addMessage({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: (message.title ? `**${message.title}**\n\n` : '') + message.content,
          type: 'voice',
          timestamp: new Date().toISOString(),
        })
        break
      case 'agent_state':
        // The agent reports its real state now, so the "no reply" safety timer can go.
        if (idleTimeoutRef.current) clearTimeout(idleTimeoutRef.current)
        if (message.state === 'thinking') setVoiceStatus('processing')
        else if (message.state === 'speaking') setVoiceStatus('speaking')
        // Ignore "idle" while the mic is held (the agent goes idle when you talk over it)
        else if (message.state === 'idle' && !useConversationStore.getState().isRecording) setVoiceStatus('idle')
        break
    }
  }, [addMessage, setVoiceStatus])

  // --- Room event setup ---

  const setupRoomEvents = useCallback((room: Room) => {
    room.on(
      RoomEvent.TrackSubscribed,
      (track: RemoteTrack, _publication: RemoteTrackPublication, _participant: RemoteParticipant) => {
        if (track.kind === Track.Kind.Audio) {
          setVoiceStatus('speaking')
          // Play agent audio
          const audioEl = track.attach()
          document.body.appendChild(audioEl)
          agentAudioElRef.current = audioEl

          // Visualize agent audio
          const mediaTrack = track.mediaStreamTrack
          if (mediaTrack) {
            connectAnalyserToTrack(mediaTrack)
            startAudioLevelMonitoring()
          }

          // Clear idle timeout since agent responded
          if (idleTimeoutRef.current) {
            clearTimeout(idleTimeoutRef.current)
            idleTimeoutRef.current = undefined
          }
        }
      },
    )

    room.on(
      RoomEvent.TrackUnsubscribed,
      (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio) {
          setVoiceStatus('idle')
          stopAudioLevelMonitoring()
          track.detach()
          if (agentAudioElRef.current) {
            agentAudioElRef.current.remove()
            agentAudioElRef.current = null
          }
        }
      },
    )

    room.on(
      RoomEvent.DataReceived,
      (payload: Uint8Array) => {
        try {
          const message: LiveKitDataMessage = JSON.parse(
            new TextDecoder().decode(payload),
          )
          handleDataMessage(message)
        } catch {
          // Ignore malformed messages
        }
      },
    )

    room.on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
      if (state === ConnectionState.Disconnected) {
        setConnectionStatus('disconnected')
        setVoiceStatus('idle')
        setIsLiveKitConnected(false)
      } else if (state === ConnectionState.Reconnecting) {
        setConnectionStatus('connecting')
      } else if (state === ConnectionState.Connected) {
        setConnectionStatus('connected')
        setIsLiveKitConnected(true)
      }
    })
  }, [
    setVoiceStatus, setConnectionStatus, connectAnalyserToTrack,
    startAudioLevelMonitoring, stopAudioLevelMonitoring, handleDataMessage,
  ])

  // --- Demo mode fallback ---

  const enterDemoMode = useCallback(async () => {
    try {
      const constraints: MediaStreamConstraints = {
        audio: audioInputDevice ? { deviceId: { exact: audioInputDevice } } : true,
      }
      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      demoStreamRef.current = stream
      const track = stream.getAudioTracks()[0]
      connectAnalyserToTrack(track)
    } catch {
      // Mic access denied — waveform stays flat
    }
  }, [audioInputDevice, connectAnalyserToTrack])

  const exitDemoMode = useCallback(() => {
    if (demoStreamRef.current) {
      demoStreamRef.current.getTracks().forEach((t) => t.stop())
      demoStreamRef.current = null
    }
  }, [])

  // --- Connection ---

  const connect = useCallback(async (): Promise<boolean> => {
    if (roomRef.current?.state === ConnectionState.Connected) return true
    if (isConnectingRef.current) return false

    isConnectingRef.current = true
    setConnectionStatus('connecting')
    setConnectionError(null)

    try {
      const { livekit_token } = await getLiveKitToken()

      const room = new Room()
      setupRoomEvents(room)
      await room.connect(LIVEKIT_URL, livekit_token)
      // Tell the agent whether to read replies aloud (it skips TTS when off)
      await room.localParticipant.setAttributes({ speak_replies: String(speakRepliesRef.current) })

      // Publish local mic track (muted initially)
      await room.localParticipant.setMicrophoneEnabled(true)
      await room.localParticipant.setMicrophoneEnabled(false)

      roomRef.current = room
      setConnectionStatus('connected')
      setIsLiveKitConnected(true)
      isConnectingRef.current = false
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to connect'
      setConnectionError(message)
      setConnectionStatus('error')
      setIsLiveKitConnected(false)
      isConnectingRef.current = false
      return false
    }
  }, [setConnectionStatus, setupRoomEvents])

  // Keep the agent in step when "Read replies aloud" changes mid-conversation
  useEffect(() => {
    speakRepliesRef.current = speakReplies
    const room = roomRef.current
    if (room?.state === ConnectionState.Connected) {
      room.localParticipant.setAttributes({ speak_replies: String(speakReplies) }).catch(() => {})
    }
  }, [speakReplies])

  // --- Public API ---

  const stopSpeaking = useCallback(() => {
    const room = roomRef.current
    if (room?.state !== ConnectionState.Connected) return
    const payload = new TextEncoder().encode(JSON.stringify({ type: 'interrupt' }))
    room.localParticipant.publishData(payload, { reliable: true, topic: CONTROL_TOPIC }).catch(() => {})
    if (useConversationStore.getState().voiceStatus === 'speaking') setVoiceStatus('idle')
  }, [setVoiceStatus])

  const startListening = useCallback(async () => {
    setRecording(true)
    setVoiceStatus('listening')

    const connected = await connect()

    if (connected && roomRef.current) {
      // Talking over Butler stops it straight away (don't wait for voice detection)
      stopSpeaking()
      // LiveKit mode: unmute local mic
      await roomRef.current.localParticipant.setMicrophoneEnabled(true)
      const micTrack = roomRef.current.localParticipant.audioTrackPublications.values().next().value
      if (micTrack?.track?.mediaStreamTrack) {
        connectAnalyserToTrack(micTrack.track.mediaStreamTrack)
      }
    } else {
      // Demo mode: capture mic directly for waveform
      await enterDemoMode()
    }

    startAudioLevelMonitoring()
  }, [
    setRecording, setVoiceStatus, connect, enterDemoMode,
    connectAnalyserToTrack, startAudioLevelMonitoring, stopSpeaking,
  ])

  const stopListening = useCallback(() => {
    setRecording(false)
    stopAudioLevelMonitoring()

    if (isLiveKitConnected && roomRef.current) {
      // LiveKit mode: mute local mic, wait for agent
      roomRef.current.localParticipant.setMicrophoneEnabled(false)
      setVoiceStatus('processing')

      // Safety timeout: if agent doesn't respond, return to idle
      idleTimeoutRef.current = setTimeout(() => {
        setVoiceStatus('idle')
      }, IDLE_TIMEOUT_MS)
    } else {
      // Demo mode: simulate processing cycle
      exitDemoMode()
      setVoiceStatus('processing')
      demoTimeoutRef.current = setTimeout(() => {
        setVoiceStatus('idle')
      }, DEMO_PROCESSING_MS)
    }
  }, [
    isLiveKitConnected, setRecording, setVoiceStatus,
    stopAudioLevelMonitoring, exitDemoMode,
  ])

  const disconnect = useCallback(() => {
    // Clear all timers
    if (idleTimeoutRef.current) clearTimeout(idleTimeoutRef.current)
    if (demoTimeoutRef.current) clearTimeout(demoTimeoutRef.current)
    stopAudioLevelMonitoring()
    exitDemoMode()

    // Disconnect LiveKit room
    if (roomRef.current) {
      roomRef.current.disconnect()
      roomRef.current = null
    }

    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }

    // Remove agent audio element
    if (agentAudioElRef.current) {
      agentAudioElRef.current.remove()
      agentAudioElRef.current = null
    }

    analyserRef.current = null
    setConnectionStatus('disconnected')
    setVoiceStatus('idle')
    setRecording(false)
    setIsLiveKitConnected(false)
    setConnectionError(null)
  }, [
    setConnectionStatus, setVoiceStatus, setRecording,
    stopAudioLevelMonitoring, exitDemoMode,
  ])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (idleTimeoutRef.current) clearTimeout(idleTimeoutRef.current)
      if (demoTimeoutRef.current) clearTimeout(demoTimeoutRef.current)
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
      if (demoStreamRef.current) {
        demoStreamRef.current.getTracks().forEach((t) => t.stop())
      }
      if (roomRef.current) {
        roomRef.current.disconnect()
      }
      if (audioContextRef.current) {
        audioContextRef.current.close()
      }
      if (agentAudioElRef.current) {
        agentAudioElRef.current.remove()
      }
    }
  }, [])

  return {
    startListening,
    stopListening,
    disconnect,
    stopSpeaking,
    audioLevels,
    connectionError,
    isLiveKitConnected,
  }
}

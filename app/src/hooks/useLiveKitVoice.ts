import { useCallback, useEffect, useRef, useState } from 'react'
import { Room, RoomEvent, ConnectionState, Track } from 'livekit-client'
import type { AudioCaptureOptions, RemoteParticipant, RemoteTrack } from 'livekit-client'
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
/** Back to idle if Butler hasn't started on a reply this long after you let go. */
const IDLE_TIMEOUT_MS = 8_000
/** Keep the mic open this long after you let go, so the last word isn't clipped.
 *  Muting is what tells Butler your turn is over (push-to-talk). */
const MIC_TAIL_MS = 300

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
  const analyserSourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const animFrameRef = useRef<number>(0)
  const idleTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const muteTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const agentAudioElRef = useRef<HTMLAudioElement | null>(null)
  const agentTrackRef = useRef<MediaStreamTrack | null>(null)
  /** The mic button is held (push-to-talk) or toggled on. */
  const pressedRef = useRef(false)
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
    analyserSourceRef.current?.disconnect()
    const source = ctx.createMediaStreamSource(new MediaStream([mediaStreamTrack]))
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 64
    source.connect(analyser)
    analyserSourceRef.current = source
    analyserRef.current = analyser
  }, [])

  const startAudioLevelMonitoring = useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser) return
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)

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

  /** Show this track (your mic, or Butler's voice) on the waveform. */
  const visualize = useCallback((track: MediaStreamTrack) => {
    connectAnalyserToTrack(track)
    startAudioLevelMonitoring()
  }, [connectAnalyserToTrack, startAudioLevelMonitoring])

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
        // The agent reports its real state, so the "no reply" safety timer can go.
        if (idleTimeoutRef.current) clearTimeout(idleTimeoutRef.current)
        // While you're holding the mic, your state wins (Butler goes idle when you talk over it)
        if (pressedRef.current) break
        if (message.state === 'thinking') {
          setVoiceStatus('processing')
        } else if (message.state === 'speaking') {
          setVoiceStatus('speaking')
          if (agentTrackRef.current) visualize(agentTrackRef.current)
        } else if (message.state === 'idle') {
          setVoiceStatus('idle')
          stopAudioLevelMonitoring()
        }
        break
    }
  }, [addMessage, setVoiceStatus, visualize, stopAudioLevelMonitoring])

  // --- Room event setup ---

  const setupRoomEvents = useCallback((room: Room) => {
    room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
      if (track.kind !== Track.Kind.Audio) return
      // Butler's voice. Its state messages drive the status and waveform.
      const audioEl = track.attach()
      document.body.appendChild(audioEl)
      agentAudioElRef.current = audioEl
      agentTrackRef.current = track.mediaStreamTrack
    })

    room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
      if (track.kind !== Track.Kind.Audio) return
      track.detach().forEach((el) => el.remove())
      agentAudioElRef.current = null
      agentTrackRef.current = null
    })

    // Butler left (e.g. the agent was redeployed): drop the room so the next
    // press opens a fresh one with a new agent, instead of talking to no one
    room.on(RoomEvent.ParticipantDisconnected, (participant: RemoteParticipant) => {
      if (participant.isAgent) room.disconnect()
    })

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
        if (roomRef.current === room) roomRef.current = null
        setConnectionStatus('disconnected')
        setIsLiveKitConnected(false)
        if (!pressedRef.current) {
          setVoiceStatus('idle')
          stopAudioLevelMonitoring()
        }
      } else if (state === ConnectionState.Reconnecting) {
        setConnectionStatus('connecting')
      } else if (state === ConnectionState.Connected) {
        setConnectionStatus('connected')
        setIsLiveKitConnected(true)
      }
    })
  }, [setVoiceStatus, setConnectionStatus, stopAudioLevelMonitoring, handleDataMessage])

  // --- Connection ---

  const micOptions = useCallback((): AudioCaptureOptions | undefined => (
    audioInputDevice ? { deviceId: audioInputDevice } : undefined
  ), [audioInputDevice])

  /**
   * Open a fresh voice room. The mic starts recording straight away, in
   * parallel with connecting, and LiveKit hands Butler what you said while it
   * was joining (the pre-connect buffer), so the first words aren't lost.
   */
  const startRoom = useCallback(async (): Promise<Room> => {
    // preConnectBuffer goes in publishDefaults: livekit-client 2.17 reads it from there
    // (merged with the capture options), not from setMicrophoneEnabled's publish options
    const room = new Room({ publishDefaults: { preConnectBuffer: true } })
    roomRef.current = room
    setupRoomEvents(room)
    setConnectionStatus('connecting')
    setConnectionError(null)

    try {
      await Promise.all([
        room.localParticipant.setMicrophoneEnabled(true, micOptions()),
        getLiveKitToken().then(({ livekit_token }) => room.connect(LIVEKIT_URL, livekit_token)),
      ])
    } catch (err) {
      if (roomRef.current === room) roomRef.current = null
      room.disconnect()
      throw err
    }

    // Tell the agent whether to read replies aloud (it skips TTS when off).
    // Not awaited: this must never cost you the conversation.
    room.localParticipant
      .setAttributes({ speak_replies: String(speakRepliesRef.current) })
      .catch((err) => console.warn('Could not send the read-aloud setting', err))
    return room
  }, [setupRoomEvents, setConnectionStatus, micOptions])

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

  /** Mute the mic once the tail has passed, unless you've pressed again. */
  const scheduleMute = useCallback(() => {
    clearTimeout(muteTimerRef.current)
    muteTimerRef.current = setTimeout(() => {
      if (pressedRef.current) return
      roomRef.current?.localParticipant.setMicrophoneEnabled(false).catch(() => {})
    }, MIC_TAIL_MS)
  }, [])

  const startListening = useCallback(async () => {
    pressedRef.current = true
    clearTimeout(muteTimerRef.current)
    if (idleTimeoutRef.current) clearTimeout(idleTimeoutRef.current)
    setRecording(true)
    setVoiceStatus('listening')
    // Talking over Butler stops it straight away
    stopSpeaking()

    try {
      const existing = roomRef.current
      const room = existing ?? await startRoom()
      if (existing) await room.localParticipant.setMicrophoneEnabled(true, micOptions())
      // Let go while connecting: mute once the tail has passed
      if (!pressedRef.current) {
        scheduleMute()
        return
      }
      const mic = room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track
      if (mic) visualize(mic.mediaStreamTrack)
    } catch (err) {
      pressedRef.current = false
      setRecording(false)
      setVoiceStatus('idle')
      setConnectionStatus('error')
      setConnectionError(err instanceof Error ? err.message : 'Failed to connect')
    }
  }, [
    setRecording, setVoiceStatus, setConnectionStatus, stopSpeaking, startRoom,
    micOptions, scheduleMute, visualize,
  ])

  const stopListening = useCallback(() => {
    if (!pressedRef.current) return
    pressedRef.current = false
    setRecording(false)
    stopAudioLevelMonitoring()

    if (!roomRef.current) {
      setVoiceStatus('idle')
      return
    }
    setVoiceStatus('processing')
    scheduleMute()
    // Safety net in case Butler never answers (e.g. nothing was said)
    idleTimeoutRef.current = setTimeout(() => {
      setVoiceStatus('idle')
    }, IDLE_TIMEOUT_MS)
  }, [setRecording, setVoiceStatus, stopAudioLevelMonitoring, scheduleMute])

  const disconnect = useCallback(() => {
    pressedRef.current = false
    // Clear all timers
    if (idleTimeoutRef.current) clearTimeout(idleTimeoutRef.current)
    clearTimeout(muteTimerRef.current)
    stopAudioLevelMonitoring()

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
    analyserSourceRef.current = null
    agentTrackRef.current = null
    setConnectionStatus('disconnected')
    setVoiceStatus('idle')
    setRecording(false)
    setIsLiveKitConnected(false)
    setConnectionError(null)
  }, [setConnectionStatus, setVoiceStatus, setRecording, stopAudioLevelMonitoring])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (idleTimeoutRef.current) clearTimeout(idleTimeoutRef.current)
      clearTimeout(muteTimerRef.current)
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
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

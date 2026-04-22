import { useCallback, useEffect, useRef, useState } from 'react'
import { AnyPacket, BasePacket, RawPacket, FeaturesPacket } from '../processing/packets'
import { N_CHANNELS, SAMPLE_RATE } from '../constants'
import { Float32CircularFIFO } from '../processing/fifo'

/** How many seconds of data to keep in the rolling display buffer. */
const DISPLAY_SECONDS = 5
const DISPLAY_SIZE    = DISPLAY_SECONDS * SAMPLE_RATE


export interface EEGFeatures {
  energy:               number
  focus:                number
  mood:                 string
  theta_beta_ratio:     number
  alpha_suppression:    number
  sustained_streak_sec: number
  is_attentive:         boolean
}

export interface UseEEGStreamResult {
  buffer:    Float32CircularFIFO | null
  features:  EEGFeatures | null
  connected: boolean
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useEEGStream(url: string): UseEEGStreamResult {
  const [, setTick]              = useState(0)
  const [connected, setConnected] = useState(false)
  const [features, setFeatures]   = useState<EEGFeatures | null>(null)

  const fifoRef = useRef<Float32CircularFIFO | null>(null)
  const wsRef   = useRef<WebSocket | null>(null)

  // ── Packet handlers (one per type) ─────────────────────────────────────────

  const onRawPacket = useCallback((packet: RawPacket): void => {
    if (!fifoRef.current) {
      fifoRef.current = new Float32CircularFIFO(DISPLAY_SIZE, N_CHANNELS)
    }

    const fifo = fifoRef.current

    // packet.channels is [n_channels][n_samples] — transpose to addChunk's
    // expected [n_samples][n_channels] format.
    const nSamples = packet.channels[0].length
    const chunk: number[][] = Array.from({ length: nSamples }, (_, i) =>
      packet.channels.map(ch => ch[i])
    )

    fifo.addChunk(chunk)
    setTick(t => t + 1)
  }, [])

  const onFeaturesPacket = useCallback((packet: FeaturesPacket): void => {
    setFeatures({
      energy:               packet.energy,
      focus:                packet.focus,
      mood:                 packet.mood,
      theta_beta_ratio:     packet.theta_beta_ratio,
      alpha_suppression:    packet.alpha_suppression,
      sustained_streak_sec: packet.sustained_streak_sec ?? 0,
      is_attentive:         packet.is_attentive ?? false,
    })
  }, [])

  // ── Router ─────────────────────────────────────────────────────────────────

  const onMessage = useCallback((ev: MessageEvent<string>): void => {
    const packet = JSON.parse(ev.data) as AnyPacket
    switch (packet.type) {
      case 'raw':      onRawPacket(packet); break
      case 'features': onFeaturesPacket(packet); break
      default: console.warn('Unknown packet type:', (packet as BasePacket).type)
    }
  }, [onRawPacket, onFeaturesPacket])

  // ── WebSocket connection ───────────────────────────────────────────────────

  useEffect(() => {
    function connect(): void {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen    = (): void => setConnected(true)
      ws.onclose   = (): void => { setConnected(false); setTimeout(connect, 2000) }
      ws.onerror   = (): void => ws.close()
      ws.onmessage = onMessage
    }

    connect()

    return (): void => { wsRef.current?.close() }
  }, [url, onMessage])

  return { buffer: fifoRef.current, features, connected }
}

# Dev Reference

Cross-language API reference and duplicated-code tracker for NEURO-RAVE.
Update this file whenever a component is changed or ported to another language.

**High-level Python EEG / mood / calibration:** see root **README.md** (Configuration, calibration CLI). Native binaries here only consume the **`NeuroRaveConfig`** subset of `constants.json`.

---

## Configuration

`config/constants.json` is the single source of truth for **values**. **Python** reads the full JSON (Spotify, mood tuning, `LINE_FREQ`, `NEURO_FEATURE_SOURCE`, calibration keys, etc.). **Native** C/C++ binaries use a **subset** via `config_load()` — only fields needed for TCP/LSL/WebSocket I/O.

| Layer | File | How |
|-------|------|-----|
| Python | `src/constants.py` | `json.loads(_config_path.read_text())` + env overrides for mode / neuro routing (see file) |
| C | `native/src/streaming/config.c` | `config_load("config/constants.json")` → `NeuroRaveConfig` |
| C++ | `native/src/streaming/config.c` | same `config_load()` via `extern "C"` in `native/include/streaming/config.h` |

`NeuroRaveConfig` (native — see `native/include/streaming/config.h`):

```c
typedef struct {
    int    n_channels;
    int    sample_rate;
    int    window_size;
    int    simulate;
    char   biosemi_host[64];
    int    biosemi_port;
    int    bytes_per_sample;
    char   ws_host[64];
    int    ws_port;
} NeuroRaveConfig;
```

**Python-only keys** (ignored by native `config_load` today): Spotify URIs, `NEURO_FEATURE_SOURCE`, `NEURO_APPLY_STABILIZER_SMOOTH`, `LINE_FREQ`, `SESSION_THETA_BETA_*`, mood thresholds, etc. Documented in **README.md** § Configuration.

---

## Cross-Language Equivalents

Every component here exists in Python, C, and C++. When behaviour changes in one,
check whether the others need updating.

### TCPSource

Blocking TCP connection to BioSemi hardware with `recv_exact`.

| | Python | C | C++ |
|-|--------|---|-----|
| **File** | `src/streaming/lslbridge.py` | `native/src/streaming/lsl_bridge_c.c` | `native/src/streaming/lsl_bridge.cpp` |
| **Header** | — | `native/include/streaming/lsl_bridge_c.h` | `native/include/streaming/lsl_bridge.h` |
| **Init** | `TCPSource(host, port)` | `TCPSource_init(&self, host, port)` | `TCPSource(host, port)` |
| **Connect** | `self.connect()` | `TCPSource_connect(&self)` | `self.connect()` |
| **Read** | `self.recv_exact(n)` → `bytes` | `TCPSource_recv_exact(&self, buf, n)` → `int` | `self.recv_exact(buf, n)` → `int` |
| **Destroy** | GC | `TCPSource_destroy(&self)` | destructor |

Behaviour: blocks on connect, retries every 2 s. `recv_exact` loops until all bytes received or returns error on disconnect.

---

### BioSemi24BitDecoder

Decodes one sample block (N×3 bytes, 24-bit little-endian signed) into floats.

| | Python | C | C++ |
|-|--------|---|-----|
| **File** | `src/streaming/lslbridge.py` | `native/src/streaming/lsl_bridge_c.c` | `native/src/streaming/lsl_bridge.cpp` |
| **Init** | `BioSemi24BitDecoder(n_channels)` | `BioSemi24BitDecoder_init(&self, n_channels)` | `BioSemi24BitDecoder(n_channels)` |
| **Decode** | `self.decode_block(raw)` → `np.ndarray` | `BioSemi24BitDecoder_decode_block(&self, raw, out_float*)` | `self.decode_block(raw)` → `vector<float>` |
| **Block size** | `self.sample_block_size` | `self.sample_block_size` | `self.sample_block_size()` |

Decode logic is identical in all three: bytes 0-2 = ch0, 3-5 = ch1, …; sign-extend from bit 23.

---

### LSLPublisher

Wraps an LSL outlet and pushes one sample at a time.

| | Python | C | C++ |
|-|--------|---|-----|
| **File** | `src/streaming/lslbridge.py` | `native/src/streaming/lsl_bridge_c.c` | `native/src/streaming/lsl_bridge.cpp` |
| **Init** | `LSLPublisher(name, type, n_ch, rate, source_id)` | `LSLPublisher_init(&self, ...)` | `LSLPublisher(name, type, n_ch, rate, source_id)` |
| **Push** | `self.push_sample(np_array)` | `LSLPublisher_push_sample(&self, float*)` | `self.push_sample(vector<float>)` |
| **Destroy** | GC | `LSLPublisher_destroy(&self)` | destructor |

All create a `cft_float32` LSL outlet named `"BioSemiEEG"` with type `"EEG"`.

---

### LSLConsumer

Resolves an LSL stream by type and pulls samples/chunks.

| | Python | C | C++ |
|-|--------|---|-----|
| **File** | `src/streaming/lslbridge.py` | `native/src/streaming/lsl_bridge_c.c` | `native/src/streaming/lsl_bridge.cpp` |
| **Init** | `LSLConsumer(stream_type="EEG")` | `LSLConsumer_init(&self, stream_type)` | `LSLConsumer(stream_type)` |
| **Get sample** | `self.get_sample()` → `(sample, ts)` | `LSLConsumer_get_sample(&self, out_float*, out_ts*)` | `self.get_sample()` → `pair<double, vector<float>>` |
| **Get chunk** | `self.get_chunk(max=512)` → `(samples, ts)` | `LSLConsumer_get_chunk(&self, flat*, ts*, max)` → `int n_pulled` | `self.get_chunk(max)` → `pair<vector<double>, vector<vector<float>>>` |
| **Destroy** | GC | `LSLConsumer_destroy(&self)` | destructor |

`get_chunk` is non-blocking in all three (timeout = 0). Data layout from LSL is row-major `[s0_ch0, s0_ch1, ..., sN_chM]`.

---

### LSLBridge

Orchestrates TCPSource → BioSemi24BitDecoder → LSLPublisher on a daemon thread.

| | Python | C | C++ |
|-|--------|---|-----|
| **File** | `src/streaming/lslbridge.py` | `native/src/streaming/lsl_bridge_c.c` | `native/src/streaming/lsl_bridge.cpp` |
| **Init** | `LSLBridge(tcp, decoder, publisher)` | `LSLBridge_init(&self, tcp*, decoder*, publisher*)` | `LSLBridge(tcp, decoder, publisher)` |
| **Start** | `self.start()` | `LSLBridge_start(&self)` | `self.start()` |
| **Thread** | `threading.Thread(daemon=True)` | `pthread_create` + `pthread_detach` | `std::thread` + `detach()` |

`start()` always blocks to connect TCP first, then launches the loop thread — same in all three.

---

### EEGWebSocketServer

FastAPI + WebSocket; may pull LSL internally **or** receive raw/feature pushes from `main.py`.

| | Python | C | C++ |
|-|--------|---|-----|
| **File** | `src/streaming/ws_server.py` | `native/src/streaming/ws_server_c.c` | `native/src/streaming/ws_server.cpp` |
| **Header** | — | `native/include/streaming/ws_server_c.h` | `native/include/streaming/ws_server.h` |
| **Init** | `EEGWebSocketServer(..., use_internal_lsl_source=True)` | `EEGWebSocketServer_init(&self, host, port)` | `EEGWebSocketServer(host, port)` |
| **Start** | `self.start()` | `EEGWebSocketServer_start(&self)` | `self.start()` |
| **LSL loops** | When `use_internal_lsl_source=True`: `_raw_loop` + `_features_loop` | `resolve_lsl_stream()` + pull | same |
| **Feature path** | `_compute_features_packet`: `DashboardFeatureState.process_window` → `neuro_raw_inputs_for_stabilizer` (optional `SpotifyFeaturePipeline`) → `stabilizer_outputs_for_mood` → `propose_mood` | — | — |
| **External producer** | `main.py` uses `use_internal_lsl_source=False`; calls `publish_raw` / `publish_features` | — | — |
| **Format JSON** | `RawPacket` / `FeaturesPacket` (`packets.py`) | raw JSON only in C++ WS today | raw JSON only |
| **Broadcast** | `_broadcast(payload)` | `broadcast()` → `lws_callback_on_writable_all_protocol` | `broadcast()` → `lws_callback_on_writable_all_protocol` |
| **WS callback** | `_ws_endpoint(websocket)` | `EEGWebSocketServer_on_event(...)` | `EEGWebSocketServer::on_event(...)` |
| **Thread** | `threading.Thread(daemon=True)` | `pthread_create` + `pthread_detach` | `std::thread` + `detach()` |
| **Service loop** | asyncio event loop | `lws_service(ctx, 5ms)` | `lws_service(ctx, 5ms)` |
| **Destroy** | GC | `EEGWebSocketServer_destroy(&self)` | destructor |

---

## RawPacket JSON Schema

All three `EEGWebSocketServer` implementations broadcast this exact format.
Defined in Python at `src/streaming/packets.py`.

```json
{
  "type":      "raw",
  "timestamp": 1234567.89,
  "channels":  [
    [ch0_s0, ch0_s1, ..., ch0_sN],
    [ch1_s0, ch1_s1, ..., ch1_sN]
  ]
}
```

Layout: **columnar** — one array per channel, each array contains all samples for that channel in time order.

---

## FeaturesPacket JSON Schema

Python `FeaturesPacket` (`src/streaming/packets.py`) — sent when feature packets are broadcast (internal LSL features loop or `publish_features` from `main.py`).

```json
{
  "type": "features",
  "timestamp": 1234567.89,
  "energy": 0.42,
  "focus": 0.61,
  "mood": "calm",
  "theta_beta_ratio": 2.84,
  "alpha_suppression": 7.2,
  "sustained_attention_index": 0.0,
  "energy_index": 0.0,
  "is_attentive": false,
  "sustained_streak_sec": 0.0
}
```

---

## Calling Convention Across Languages

Same method name in all three; only call syntax changes:

| Python | C | C++ |
|--------|---|-----|
| `obj.method(args)` | `StructName_method(&obj, args)` | `obj.method(args)` |
| `obj.field` | `obj.field` | `obj.field()` (getter) or `obj.field_` |
| constructor | `StructName_init(&obj, args)` | `StructName(args)` |
| destructor (GC) | `StructName_destroy(&obj)` | `~StructName()` |

---

## Not Yet Ported

Python-only EEG / mood / Spotify stack (native WS bridge sends **raw** packets only today).

| Component | Python location | Notes |
|-----------|----------------|-------|
| `EEGProcessor` | `main.py` | Wraps `DashboardFeatureState` + `MirrorCircleFIFO` for the main loop |
| `DashboardFeatureState` | `src/processing/dashboard_features.py` | 1 s window: notch `LINE_FREQ`, bands, α suppression %, streak, variability |
| `neuro_raw_inputs_for_stabilizer` | `src/processing/neuro_raw_inputs.py` | `NEURO_FEATURE_SOURCE`: attention indices vs `SpotifyFeaturePipeline` |
| `stabilizer_outputs_for_mood` | `src/processing/mood_prepare.py` | `NEURO_APPLY_STABILIZER_SMOOTH`: EMA vs `direct_for_mood` |
| `SpotifyFeaturePipeline` | `src/processing/spotify_feature_pipeline.py` | Band-derived `NeuroFeatures`; optional session θ/β calibration |
| `MirrorCircleFIFO` / `MirrorCircleFIFO.from_seconds` | `src/processing/fifo.py` | Ring buffer; mirrored variant for windowed reads |
| `propose_mood()` / `classify_mood()` | `src/music_gen/spotify_controller.py` | Buckets: `calm`, `deep_focus`, `focus`, `hype`; `deep_focus` URIs fall back to `focus` |
| `MoodStabilizer` | `src/music_gen/spotify_controller.py` | `smooth` / `direct_for_mood`; majority vote (`SPOTIFY_MOOD_*` env) |
| Spotify controllers | `src/music_gen/spotify_controller.py`, `spotify_pool_controller.py` | Mood → playback |
| Calibration CLI | `scripts/calibration_run.py`, `src/calibration/*` | BDF replay, reports, optional search |
| `FeaturesPacket` broadcast | `src/streaming/ws_server.py` | Feature JSON (C/C++ WS server: raw only) |

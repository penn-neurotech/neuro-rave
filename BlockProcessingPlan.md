# Unified Block Processing Pipeline

> **Scope:** native C++ **audio** block processing (FIFO → block DSP → overlap-add). The Python **EEG → features → mood → Spotify** stack lives in the repo [README.md](README.md) (Configuration / EEG features) and [docs/dev-reference.md](docs/dev-reference.md) (Python-only components).

## Context

The native audio pipeline currently runs: **producer → input FIFO → AudioWriter callback → speakers** ([main.cpp:14-82](native/main.cpp), [audio_writer.cpp:20](native/src/audio/audio_writer.cpp#L20)). There is no place for user DSP work — the audio callback pulls straight from the input FIFO.

The user wants a block-based STFT-style pipeline:

```
input FIFO ──┐                                        ┌── output FIFO → AudioWriter
             │  BlockReader    user processing        │
             └─▶ poll+read ─▶ (FFT → ... → IFFT) ─▶  OLA ─┘
             (hop-triggered)                      (window-sum)
```

Output audio is emitted in `hopSize` chunks, lagging input by `blockSize - hopSize` (plus one hop of block-readiness latency).

Existing scaffolding to reuse:
- [FIFO refactor](native/include/processing/fifo.h#L19-L57) — monotonic `writeIdx`, `getTotalWritten()` lets `BlockReader` detect new-sample counts with zero ambiguity.
- `BlockReader<T>` declared at [fifo.h:229-256](native/include/processing/fifo.h#L229-L256) but not implemented.
- `applyWindow(ChannelArrayView, windowType)` declared at [fifo.h:17](native/include/processing/fifo.h#L17) but not implemented.
- `ChannelArrayBuffer` / `ChannelArrayView` / `ChannelArrayConstView` in [channel_array.h](native/include/processing/channel_array.h) — use for all block-shaped scratch storage.
- `MultiSignalFIFO<MirrorCircularFIFO>` for the output FIFO so `AudioWriter::readNSamplesInterleaved` stays zero-copy.

## Decisions (from clarification)

1. **Processing runs on a dedicated thread.** Audio callback stays lock-free and allocation-free.
2. **OLA lives in a dedicated `OverlapAddBuffer` accumulator.** FIFOs remain write-only; DSP state stays out of them.
3. **Caller owns both FIFOs.** `main.cpp` constructs input+output FIFOs, passes references to `BlockProcessor` and `AudioWriter`.

## Approach

Introduce three new pieces instead of a standalone `BlockWriter`:

### 1. Finish `BlockReader<T>` ([fifo.h:229](native/include/processing/fifo.h#L229), [fifo.cpp](native/src/processing/fifo.cpp))

- Fix the broken stub (bare `if`, missing `;` on ctor, the uninitialized `lastSeenTotal` reference).
- Add `int64_t lastSeenTotal` member (init to `fifo->getChannel(0).getTotalWritten()` at construction so first `poll()` doesn't fire on stale data).
- `poll()` logic:
  ```
  total = fifo->getChannel(0).getTotalWritten();
  newSamples = (int)(total - lastSeenTotal);
  lastSeenTotal = total;
  return counter.incrementByN(newSamples);   // counter resetThresh == hopSize
  ```
- `readBlock(const ChannelArrayView& out, windowType)`: calls `fifo->readNSamples(out, blockSize)` then `applyWindow(out, windowType)`.
- Because `BlockReader` is a template, definitions live in the header (alongside the existing template code in `MultiSignalFIFO`).

### 2. Implement `applyWindow` ([fifo.cpp](native/src/processing/fifo.cpp))

Minimal set for now: `"rectangular"` (no-op), `"hann"`, `"hamming"`. Multiplies each channel element-wise by a precomputed window. Keep it allocation-free on the hot path — window coefficients should be cached by `BlockProcessor`, not recomputed per call. **Simplification:** move `applyWindow` to take a precomputed `std::span<const float>` of coefficients; `BlockProcessor` owns the cache and passes it in. Drop the string-based dispatch from the hot path.

### 3. New class: `OverlapAddBuffer` (new file: [native/include/processing/overlap_add.h](native/include/processing/overlap_add.h))

Owns a `ChannelArrayBuffer` of shape `(nChannels, blockSize)` holding the running sum.

```cpp
class OverlapAddBuffer {
public:
    OverlapAddBuffer(int nChannels, int blockSize, int hopSize);

    // Add a processed block into the accumulator. block shape: (nChannels, blockSize).
    void addBlock(const ChannelArrayConstView& block);

    // Pop the oldest hopSize samples per channel into `out` (shape (nChannels, hopSize)).
    // Zeros the popped region and advances the accumulator.
    void popHop(const ChannelArrayView& out);

private:
    ChannelArrayBuffer accum;
    int blockSize, hopSize;
};
```

Semantics:
- `addBlock` does `accum[ch][i] += block[ch][i]` for `i in [0, blockSize)`.
- `popHop` copies `accum[ch][0..hopSize)` to `out`, then shifts `accum[ch]` left by `hopSize` and zero-fills the trailing `hopSize` samples. One `memmove` + one `memset` per channel.

No heap allocation after construction.

### 4. New class: `BlockProcessor<T>` (declared in [fifo.h](native/include/processing/fifo.h) or new [block_processor.h](native/include/processing/block_processor.h); template so defs in header)

Unifies reader + OLA + output push + user callback + its own processing thread.

```cpp
template<typename T>
class BlockProcessor {
public:
    using ProcessFn = std::function<void(const ChannelArrayConstView& in,
                                         const ChannelArrayView& out)>;

    BlockProcessor(MultiSignalFIFO<T>* inFifo,
                   MultiSignalFIFO<MirrorCircularFIFO>* outFifo,
                   int blockSize, int hopSize,
                   const std::string& windowType,
                   ProcessFn processFn);
    ~BlockProcessor();   // joins thread

    void start();        // spawns processing thread
    void stop();         // sets running=false, joins

private:
    void runLoop();      // tight poll/sleep loop on the processing thread

    BlockReader<T> reader;
    OverlapAddBuffer ola;
    ChannelArrayBuffer inBlock;     // (nChannels, blockSize) — windowed input
    ChannelArrayBuffer outBlock;    // (nChannels, blockSize) — processed output
    ChannelArrayBuffer hopOut;      // (nChannels, hopSize)   — OLA pop target
    std::vector<float> windowCoeffs;  // precomputed once
    ProcessFn processFn;
    std::atomic<bool> running{false};
    std::thread worker;
};
```

`runLoop`:
```
while (running) {
    if (reader.poll()) {
        reader.readBlock(inBlock.view(), windowCoeffs);   // windowed read
        processFn(inBlock.view(), outBlock.view());       // user FFT/process/IFFT
        ola.addBlock(outBlock.view());
        ola.popHop(hopOut.view());
        outFifo->addChunk(hopOut.view());                 // per-channel addChunk
    } else {
        std::this_thread::sleep_for(200us);   // cheap backoff; later: condvar
    }
}
```

All allocations done at construction. User's `processFn` is their future FFT code.

## Why this over a standalone BlockWriter

A `BlockWriter` class in isolation can't own OLA state — the "tail" of the previous block waiting to be summed with the next lives between reading and writing. Making `BlockProcessor` the coordinator keeps that state in one place, keeps the user's only injection point the `ProcessFn`, and keeps FIFOs generic (no `addChunkSummed` creep).

## Files to modify / create

| File | Change |
| --- | --- |
| [native/include/processing/fifo.h](native/include/processing/fifo.h) | Fix `BlockReader` stub; add `lastSeenTotal`; define `poll()`/`readBlock()` inline (template). Change `applyWindow` signature to take `std::span<const float>` coeffs. |
| [native/src/processing/fifo.cpp](native/src/processing/fifo.cpp) | Implement `applyWindow` (rectangular/hann/hamming coefficient-generator helper + the elementwise multiply). |
| [native/include/processing/overlap_add.h](native/include/processing/overlap_add.h) | **New.** `OverlapAddBuffer` class (header-only is fine; short impl). |
| [native/include/processing/block_processor.h](native/include/processing/block_processor.h) | **New.** `BlockProcessor<T>` template (header-only). |
| [native/main.cpp](native/main.cpp) | Construct output `MultiSignalFIFO<MirrorCircularFIFO>`; construct `BlockProcessor` with a pass-through `processFn` (identity) for now; call `processor.start()`; wire `AudioWriter` to the output FIFO instead of the input FIFO. |
| [native/CMakeLists.txt](native/CMakeLists.txt) | Add new headers to install targets if needed (check if globbed). |

## Verification

1. **Build:** `cmake -B build && cmake --build build` — no errors, no warnings from new code.
2. **Pass-through sanity check:** wire `BlockProcessor` with an identity `processFn` (copy `in` → `out`) and `windowType = "hann"`, `blockSize = 1024`, `hopSize = 512`. With a sine-wave Synthesizer source, the audio output should sound identical to the input (OLA of overlapping Hann windows with 50% hop reconstructs the signal perfectly — this is the standard COLA sanity check).
3. **Latency check:** measure wall-clock delay between producer push and audio callback consumption — should be ≈ `(blockSize - hopSize) + hopSize` samples + OS buffer.
4. **Underrun check:** run for 60s under `log` instrumentation in `AudioWriter::dataCallback` — output FIFO should never be drained faster than the processing thread fills it (i.e. no glitches).
5. **Unit-level:** small standalone test for `OverlapAddBuffer` — push two overlapping rectangular blocks, confirm popped hop samples sum correctly.

## Out of scope for this plan

- The actual FFT/IFFT implementation (user will write later — `processFn` is the injection point).
- Condition-variable wakeups in the processing thread (start with sleep backoff; easy to upgrade later).
- Variable hop sizes, time-varying windows, perfect-reconstruction edge cases beyond COLA.

---

# Future buffer work

Additional buffer types likely needed as the DSP suite grows, ranked roughly by priority.

### 1. Make all FIFOs thread-safe by default (SPSC)
Current `CircularFIFO` / `MirrorCircularFIFO` are **not thread-safe** — audio callback and producer/processing threads race on `writeIdx` and `data`. Works on x86 by accident, formally UB. Every FIFO in this pipeline is crossed between threads (producer → processing, processing → audio callback), so there is no legitimate use case for a non-atomic FIFO.

**Retrofit, don't fork.** Make the existing `CircularFIFO` and `MirrorCircularFIFO` thread-safe rather than introducing a parallel `SPSCRingFIFO` class:
- Change `writeIdx` to `std::atomic<int64_t>`; add `std::atomic<int64_t> readIdx` for SPSC consumer-side tracking.
- Writes: `data[w & mask] = sample;` then `writeIdx.store(w + 1, std::memory_order_release);`.
- Reads: `auto w = writeIdx.load(std::memory_order_acquire);` before touching data.
- `getTotalWritten()` becomes an acquire load.
- On x86, acquire/release are ordinary `MOV`; the only cost is blocking compiler reordering. Negligible at audio-callback rates.
- Keep the same monotonic-counter + power-of-two-mask pattern.

Plain (non-atomic) buffers stay plain for intra-thread state: `DelayLine`, `OverlapAddBuffer`, filter internal state. These never cross threads, so atomics would be pure overhead and noise.

### 2. `DelayLine`
Random access by delay amount, not by "most recent n". Interface is fundamentally different from FIFO read semantics — separate class.
- `addSample(x)`, `sample(int delay) const`, optionally `sample(float delay) const` with linear/Lagrange interpolation.
- Reuses the same power-of-two ring storage as FIFO.

### 3. `OverlapSaveBuffer`
Dual of `OverlapAddBuffer`. For partitioned FFT convolution (long FIRs, convolution reverb). Structure will mirror `OverlapAddBuffer` closely — plan to keep them in the same directory / naming family.

### 4. `ParamBuffer<T>` (atomic double-buffer for parameter state)
Separate from signal buffers. For GUI/API → audio thread param publishing. Audio thread reads a published snapshot; writer fills a back buffer; atomic pointer swap. Keeps the audio callback lock-free under parameter changes. Not related to signal storage at all.

### 5. `BlockFIFO` / per-block queue
Decouples `BlockProcessor` from downstream consumers if the processing thread ever falls behind. Low priority; revisit if underruns become a problem.

### 6. `Wavetable`
Read-only lookup with phase-based indexing. Relevant if oscillators move from math-based (`sin(phase)`) to table-based for perf. Different interface entirely — no `addSample`. Only useful once synthesis becomes a hot path.

---

## Design decisions to lock in NOW to keep these cheap to add

These are one-time calls that, if made early, let new buffer types slot in without refactors. Each is a current state of the code; codify it so future additions conform.

### Locked in (via current `FIFO` refactor)

- **Power-of-two sizes with `mask = size - 1` masking** is the house ring-buffer convention. Any new ring-based buffer (`SPSCRingFIFO`, `DelayLine`) enforces this in its constructor (via existing `isPowerOfTwo` helper at [fifo.cpp:8](native/src/processing/fifo.cpp#L8)).
- **Monotonic `int64_t writeIdx` + `getTotalWritten()` accessor.** Any producer-side buffer exposes this so downstream block readers can compute exact new-sample deltas without wraparound ambiguity.
- **`ChannelArrayView` / `ChannelArrayConstView` are the block I/O currency.** All block-shaped reads/writes across the suite use these; don't introduce parallel view types.

### Decision: do NOT create a grand unified `Buffer` abstract base class

Tempting, but these buffer types have fundamentally different access patterns:
- FIFO: "read most-recent N" (non-destructive) + `getFilledSize`
- SPSC ring: "consume N" (destructive) + `availableRead` / `availableWrite`
- DelayLine: "sample at delay D" (random access)
- Wavetable: read-only, phase-indexed, no writes

Forcing a shared vtable means a lowest-common-denominator interface that helps nobody and blocks performance-critical specialization (e.g. `MirrorCircularFIFO::peekNSamples` returning `std::span<const float>` for zero-copy). **Keep families separate**; `FIFO` stays the abstract base of the FIFO family only.

### Decision: share storage via composition, not inheritance

When the second ring-based buffer arrives (almost certainly `DelayLine`), extract a small **`RingStorage`** helper. `RingStorage` owns only the buffer and the power-of-two masking trick — **no indices, no atomics, no FIFO semantics**. Each consumer supplies its own access policy on top.

Concrete sketch (target shape for the extraction, not code to write today):

```cpp
struct RingStorage {
    std::vector<float> data;
    int size;
    int mask;

    explicit RingStorage(int size);   // throws if not power-of-two

    // Logical index → physical slot. idx can be any int64_t; mask wraps it.
    float&       at(int64_t idx)       { return data[idx & mask]; }
    const float& at(int64_t idx) const { return data[idx & mask]; }

    // Wrap-aware chunk copy starting at logical position beginIdx.
    // Handles the split across the physical wrap internally.
    void writeChunk(std::span<const float> chunk, int64_t beginIdx);
    void readChunk(std::span<float> out,  int64_t beginIdx) const;
};
```

Consumers layer their own policy on top:

```cpp
class CircularFIFO {
    RingStorage storage;
    std::atomic<int64_t> writeIdx;
    std::atomic<int64_t> readIdx;
    // FIFO-shaped API: addSample/addChunk/readNSamples/readAll/getTotalWritten
};

class DelayLine {
    RingStorage storage;
    int64_t writeIdx = 0;       // plain, intra-thread
    void  add(float x)         { storage.at(writeIdx++) = x; }
    float sample(int d) const  { return storage.at(writeIdx - 1 - d); }
};
```

What moves: the current `FIFO::data`, `FIFO::mask`, and the wrap-aware `writeDataByRange` / `readDataByRange` logic in [fifo.cpp](native/src/processing/fifo.cpp) all migrate into `RingStorage`. `FIFO` keeps only `channelName`, atomic indices, and the FIFO-shaped API. `MirrorCircularFIFO` gets a sibling `MirrorRingStorage` (double-length; writes update both halves for the zero-copy peek trick).

**Do not extract preemptively.** Currently only `CircularFIFO` / `MirrorCircularFIFO` exist and they already share via inheritance from `FIFO`. Extracting `RingStorage` before `DelayLine` exists is speculative generality. Trigger the extraction when the second consumer is about to be written so the shape is pinned down by two real use cases.

### Decision: `BlockReader` / `BlockProcessor` / consumers are templated on buffer type, documented via a C++20 concept

Already partly true (`BlockReader<T>`). Formalize the contract so new buffer types know exactly what to expose to be consumable:

```cpp
template<typename B>
concept BlockReadable = requires(B b, std::span<float> s) {
    { b.readNSamples(s) }     -> std::same_as<void>;
    { b.getTotalWritten() }    -> std::same_as<int64_t>;
    { b.size }                 -> std::convertible_to<int>;
};
```

Add this concept to [fifo.h](native/include/processing/fifo.h) alongside `BlockReader`. It makes template-error messages readable and documents the contract explicitly.

### Decision: FIFOs are thread-safe by default; plain buffers for intra-thread state only

- **FIFOs (`CircularFIFO`, `MirrorCircularFIFO`)** get atomic `writeIdx`/`readIdx` and acquire/release ordering. Perf cost is negligible (ordinary MOV on x86; a single `dmb ish` on ARM) relative to the actual sample copy, and every FIFO in this pipeline crosses threads anyway.
- **Intra-thread stateful buffers (`DelayLine`, `OverlapAddBuffer`, filter state)** stay plain (non-atomic). They live inside a single thread by construction; atomics would be noise.
- Do **not** introduce a parallel "SPSC" class alongside the non-atomic one — two classes doing the same job with a subtle correctness trap between them. One FIFO, thread-safe.

### Deferred decisions (not urgent, but worth being aware)

- Whether `MultiSignalFIFO<T>` should be generalized to `MultiSignal<T>` and reused for `MultiSignalDelayLine` etc. Likely yes when the second use case appears — the per-channel wrapping pattern is worth reusing.
- Whether to introduce an allocator abstraction for buffer storage (for real-time `<memory>`-pool allocations). Defer until a concrete real-time allocation pain point shows up.
- Whether to expose raw pointer / `std::span` access to internal storage on new types the way `MirrorCircularFIFO::peekNSamples` does. Case-by-case — only when a zero-copy hot path needs it.

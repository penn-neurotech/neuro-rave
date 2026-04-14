#include <vector>
#include <span>
#include <string>
#include <stdexcept>
#include <algorithm>
#include "fifo.h"

bool isPowerOfTwo(int n) {
    return (n != 0) && ((n & (n - 1)) == 0);
}

int secondsToSamples(float seconds, int sampleRate) {
    return int(seconds * sampleRate);
}

float samplesToSeconds(int samples, int sampleRate) {
     return samples / float(sampleRate);
}

void applyWindow(const ChannelArrayView& data, const std::string& windowType);

// FIFO base class
FIFO::FIFO(int size, const std::string& channelName)
    : size(size), mask(size - 1), channelName(channelName), data(size, 0.f), writeIdx(0) {
    if (!isPowerOfTwo(size)) {
        throw std::invalid_argument(
            "FIFO size (" + std::to_string(size) + ") must be a power of two");
    }
}

void FIFO::validateRange(int begin, int end, int maxSize, const std::string& name) {
    if (begin < 0 || end > maxSize || begin > end) {
        throw std::out_of_range(
            name + " range [" + std::to_string(begin) + ":" + std::to_string(end) +
            "] out of bounds for size " + std::to_string(maxSize));
    }
}

void FIFO::writeDataByRange(std::span<const float> source,
                             int sourceBegin, int sourceEnd,
                             int dataBegin) {
    if (sourceEnd == -1) sourceEnd = static_cast<int>(source.size());
    int copyLen = sourceEnd - sourceBegin;

    validateRange(sourceBegin, sourceEnd, static_cast<int>(source.size()), "source");
    validateRange(dataBegin, dataBegin + copyLen, static_cast<int>(data.size()), "data");

    std::copy(source.begin() + sourceBegin, source.begin() + sourceEnd,
              data.begin() + dataBegin);
}

void FIFO::readDataByRange(std::span<float> result,
                            int dataBegin, int dataEnd,
                            int resultBegin) const {
    if (dataEnd == -1) dataEnd = static_cast<int>(data.size());
    int copyLen = dataEnd - dataBegin;

    validateRange(dataBegin, dataEnd, static_cast<int>(data.size()), "data");
    validateRange(resultBegin, resultBegin + copyLen, static_cast<int>(result.size()), "result");

    std::copy(data.begin() + dataBegin, data.begin() + dataEnd,
              result.begin() + resultBegin);
}

int FIFO::getFilledSize() const {
    return writeIdx < size ? static_cast<int>(writeIdx) : size;
}

// CircularFIFO
CircularFIFO::CircularFIFO(int size, const std::string& channelName)
    : FIFO(size, channelName) {}

void CircularFIFO::addSample(float sample) {
    data[writeIdx & mask] = sample;
    writeIdx++;
}

void CircularFIFO::addChunk(std::span<const float> chunk) {
    int nSamples = static_cast<int>(chunk.size());

    if (nSamples > size) {
        throw std::invalid_argument(
            "Chunk size (" + std::to_string(nSamples) +
            ") is larger than buffer size (" + std::to_string(size) +
            ". This could lead to data loss. Split chunk into multiple chunks)");
    }

    int w = static_cast<int>(writeIdx & mask);
    int end = w + nSamples;
    if (end <= size) {
        writeDataByRange(chunk, 0, nSamples, w);
    } else {
        int first = size - w;
        writeDataByRange(chunk, 0, first, w);
        writeDataByRange(chunk, first, nSamples, 0);
    }

    writeIdx += nSamples;
}

void CircularFIFO::readNSamples(std::span<float> out) {
    int n = static_cast<int>(out.size());
    if (n > size) n = size;

    int w = static_cast<int>(writeIdx & mask);
    int start = (w - n + size) & mask;

    if (start + n <= size) {
        readDataByRange(out, start, start + n, 0);
    } else {
        int tail = size - start;
        readDataByRange(out, start, size, 0);
        readDataByRange(out, 0, n - tail, tail);
    }
}

void CircularFIFO::readAll(std::span<float> out) {
    if (static_cast<int>(out.size()) < size) {
        throw std::invalid_argument("readAll output buffer too small");
    }
    int w = static_cast<int>(writeIdx & mask);
    int tail = size - w;
    readDataByRange(out, w, size, 0);
    readDataByRange(out, 0, w, tail);
}

// MirrorCircularFIFO — `size` is the logical capacity. The underlying `data`
// vector is sized to 2*size so the n most-recent samples are always contiguous.
MirrorCircularFIFO::MirrorCircularFIFO(int size, const std::string& channelName)
    : FIFO(size, channelName) {
    data.assign(static_cast<size_t>(size) * 2, 0.f);
}

void MirrorCircularFIFO::addSample(float sample) {
    int w = static_cast<int>(writeIdx & mask);
    data[w] = sample;
    data[w + size] = sample;
    writeIdx++;
}

void MirrorCircularFIFO::addChunk(std::span<const float> chunk) {
    int nSamples = static_cast<int>(chunk.size());

    if (nSamples > size) {
        throw std::invalid_argument(
            "Chunk size (" + std::to_string(nSamples) +
            ") is larger than buffer size (" + std::to_string(size) +
            ". This could lead to data loss. Split chunk into multiple chunks)");
    }

    int w = static_cast<int>(writeIdx & mask);
    int end = w + nSamples;
    if (end <= size) {
        writeDataByRange(chunk, 0, nSamples, w);
        writeDataByRange(chunk, 0, nSamples, w + size);
    } else {
        int first = size - w;
        writeDataByRange(chunk, 0, first, w);
        writeDataByRange(chunk, 0, first, w + size);
        writeDataByRange(chunk, first, nSamples, 0);
        writeDataByRange(chunk, first, nSamples, size);
    }

    writeIdx += nSamples;
}

std::span<const float> MirrorCircularFIFO::peekNSamples(int n) const {
    if (n > size) n = size;
    int w = static_cast<int>(writeIdx & mask);
    int start = w + size - n;
    return std::span<const float>(data.data() + start, static_cast<size_t>(n));
}

void MirrorCircularFIFO::readNSamples(std::span<float> out) {
    int n = static_cast<int>(out.size());
    auto src = peekNSamples(n);
    std::copy(src.begin(), src.end(), out.begin());
}

void MirrorCircularFIFO::readAll(std::span<float> out) {
    if (static_cast<int>(out.size()) < size) {
        throw std::invalid_argument("readAll output buffer too small");
    }
    int w = static_cast<int>(writeIdx & mask);
    readDataByRange(out, w, w + size, 0);
}

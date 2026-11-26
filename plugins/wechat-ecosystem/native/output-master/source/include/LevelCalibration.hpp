#pragma once

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <vector>

namespace om {
using SampleFrame = std::array<float, 2>;
constexpr std::array<float, 5> calibrationTargets{-22, -18, -14, -11, -8};
// Revision, five drive adjustments in dB, then the learned 250 Hz body adjustment.
using Calibration = std::array<float, calibrationTargets.size() + 2>;
inline float levelCorrection(const Calibration& curve, float target) {
    if (curve[0] != 1) return 0;
    for (size_t i = 1; i < calibrationTargets.size(); ++i) {
        if (target <= calibrationTargets[i]) {
            const float w = std::clamp((target-calibrationTargets[i-1]) /
                                       (calibrationTargets[i]-calibrationTargets[i-1]), 0.f, 1.f);
            return std::lerp(curve[i],curve[i+1],w);
        }
    }
    return curve[calibrationTargets.size()];
}

// One render writer and a non-realtime reader. Slot claims never block the writer.
// Swapping a completed half-second block costs O(1), including at 384 kHz.
class CalibrationSampler {
    struct Slot {
        std::atomic<unsigned> owner{0};
        uint32_t generation = 0;
        uint64_t sequence = 0;
        std::vector<SampleFrame> data;
    };
    static_assert(std::atomic<unsigned>::is_always_lock_free);
    static constexpr unsigned slotsCount = 32;
    std::array<Slot,slotsCount> slots;
    std::vector<SampleFrame> scratch;
    uint32_t generation = 0;
    uint64_t chunks = 0, random = 0;
    size_t filled = 0;
    double energy = 0;
public:
    void prepare(double rate) {
        const size_t length = size_t(std::lround(rate * 0.5));
        scratch.resize(length);
        for (auto& slot : slots) {
            slot.data.resize(length);
            slot.generation = 0;
        }
        start(0);
    }
    void start(uint32_t token) {
        generation = token;
        chunks = filled = 0;
        random = 0x631256cd7c926ad1ULL;
        energy = 0;
    }
    void push(SampleFrame frame, double weightedEnergy) {
        if (scratch.empty()) return;
        scratch[filled++] = frame;
        energy += weightedEnergy;
        if (filled != scratch.size()) return;
        const bool audible = energy / filled > 1e-7;
        filled = 0;
        energy = 0;
        if (!audible) return;
        ++chunks;
        uint64_t position = chunks - 1;
        if (position >= slotsCount) {
            // SplitMix64, fixed seed per Learn. Later material has equal inclusion probability.
            uint64_t x = (random += 0x9e3779b97f4a7c15ULL);
            x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
            x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
            position = (x ^ (x >> 31)) % chunks;
            if (position >= slotsCount) return;
        }
        auto& slot = slots[position];
        unsigned expected = 0;
        if (!slot.owner.compare_exchange_strong(expected,1,std::memory_order_acquire)) return;
        scratch.swap(slot.data);
        slot.sequence = chunks;
        slot.generation = generation;
        slot.owner.store(0,std::memory_order_release);
    }
    // Runs on the Apply thread. Allocation is outside the slot claims.
    std::vector<SampleFrame> snapshot(uint32_t token, size_t length) {
        struct Captured { uint64_t sequence; std::vector<SampleFrame> frames; };
        std::vector<Captured> found;
        found.reserve(slotsCount);
        std::vector<SampleFrame> copy(length);
        for (auto& slot : slots) {
            unsigned expected = 0;
            if (!slot.owner.compare_exchange_strong(expected,2,std::memory_order_acquire)) continue;
            const bool current = slot.generation == token && slot.data.size() == length;
            const uint64_t seq = slot.sequence;
            if (current) std::copy(slot.data.begin(),slot.data.end(),copy.begin());
            slot.owner.store(0,std::memory_order_release);
            if (current) {
                found.push_back({seq,std::move(copy)});
                copy.resize(length);
            }
        }
        std::sort(found.begin(),found.end(),[](const Captured& a,const Captured& b){return a.sequence < b.sequence;});
        std::vector<SampleFrame> result;
        result.reserve(found.size() * length);
        for (auto& chunk : found) {
            // A short crossfade to silence on discontinuous excerpts keeps splices out of the loudness probe.
            const size_t fade = std::max<size_t>(1,length/100);
            for (size_t i = 0; i < fade; ++i) {
                const float weight = float(i)/fade;
                for (unsigned ch = 0; ch < 2; ++ch) {
                    chunk.frames[i][ch] *= weight;
                    chunk.frames[length-1-i][ch] *= weight;
                }
            }
            result.insert(result.end(),chunk.frames.begin(),chunk.frames.end());
        }
        return result;
    }
};
}

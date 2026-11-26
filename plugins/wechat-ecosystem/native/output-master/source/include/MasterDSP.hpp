#pragma once

#include "LevelCalibration.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <numbers>

namespace om {

inline float gain(float db) { return std::pow(10.0f, db / 20.0f); }
inline float db(double power) { return float(10.0 * std::log10(std::max(1e-15, power))); }
inline float loudness(double power) { return std::max(-100.0f, db(power) - 0.691f); }
inline float bounded(float value, float low, float high, float fallback = 0) {
    return std::isfinite(value) ? std::clamp(value, low, high) : fallback;
}

enum Parameter : unsigned { character, autoEQ, target, width, exciter, low, focus, air,
                            lowHz, focusHz, airHz, customEQ, parameterCount };
struct ParameterInfo { const char* name; float minimum, maximum, initial; };
inline constexpr ParameterInfo parameters[] = {
    {"Character", 0, 3, 0}, {"Auto EQ", 0, 100, 100}, {"Target", -22, -8, -14},
    {"Width", 0, 150, 100}, {"Exciter", 0, 100, 0},
    {"Low", -6, 6, 0}, {"Focus", -6, 6, 0}, {"Air", -6, 6, 0},
    {"Low frequency", 20, 200, 150}, {"Focus frequency", 200, 8000, 1200},
    {"Air frequency", 8000, 20000, 10000}, {"Custom EQ", 0, 1, 1}
};
inline constexpr float eqFrequencies[] = { 150, 1200, 5600 };

enum Property : unsigned { commandProperty = 77000, displayProperty, spectrumProperty, meterProperty, toneProperty };
enum Command : uint32_t { learn = 1, apply, cancel, auditionDry, auditionMatch, resetMeters, startMeters, pauseMeters };
struct MeterInfo { float momentary = -100, range = -100; uint32_t running = 1; };
enum ProfileField : unsigned { sourceLU, lowCorrection, focusCorrection, airCorrection,
                               autoWidth, sourceCrest, profileValid, profileSize };
using Profile = std::array<float, profileSize>;
inline constexpr Profile emptyProfile{ -100, 0, 0, 0, 1, 0, 0 };

enum Status : uint32_t { readyToLearn, listening, canApply, needsAudio, mastered };
struct Display {
    Profile active = emptyProfile;
    float seconds = 0;
    float inputLU = -100;
    float outputLU = -100;
    float shortLU = -100;
    float truePeak = -100;
    float reduction = 0;
    float correlation = 0;
    uint32_t status = readyToLearn;
    uint32_t dry = 0;
    uint32_t match = 0;
};

// One writer per publication. Readers never block or retry on the audio thread.
template<size_t Count>
class Publication {
    static_assert(std::atomic<float>::is_always_lock_free);
    std::atomic<uint32_t> generation{0};
    std::array<std::atomic<float>, Count> fields{};
public:
    void write(const std::array<float, Count>& values) {
        generation.fetch_add(1);
        for (size_t i = 0; i < Count; ++i) fields[i].store(values[i]);
        generation.fetch_add(1);
    }
    bool read(std::array<float, Count>& values) const {
        auto before = generation.load();
        if (before & 1) return false;
        auto snapshot = values;
        for (size_t i = 0; i < Count; ++i) snapshot[i] = fields[i].load();
        if (before != generation.load()) return false;
        values = snapshot;
        return true;
    }
};

enum FilterShape { lowShelf, bell, highShelf, lowPass, highPass, bandPass };
struct Coefficients {
    double b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
    static Coefficients make(FilterShape shape, double rate, double hz, double q, double amount = 0);
    static Coefficients meterShelf(double rate);
    static Coefficients meterHighPass(double rate);
    float magnitude(double rate, double hz) const;
};
std::array<Coefficients, 3> autoSections(double rate, const std::array<float,3>& gain, bool modern);
struct Biquad {
    double z1 = 0, z2 = 0;
    float run(float input, const Coefficients& c) {
        const double value = c.b0 * input + z1;
        z1 = c.b1 * input - c.a1 * value + z2;
        z2 = c.b2 * input - c.a2 * value;
        if (std::abs(z1) < 1e-25) z1 = 0;
        if (std::abs(z2) < 1e-25) z2 = 0;
        return float(value);
    }
};

// Parameter IDs and their original response are retained for recalled 0.1 sessions.
struct CharacterStyle { float low, mid, air, ratio, thresholdOffset, color, leveling, targetOffset; };
inline constexpr std::array<CharacterStyle,4> legacyStyles{{
    {0,0,0,1.30f,0,0,0,0}, {0.55f,0,-0.25f,1.45f,3,0.10f,0,0},
    {-0.15f,0.55f,0.15f,1.85f,-1,0.05f,0,0}, {0,-0.15f,0.45f,1.18f,1,0,0,0}
}};
inline constexpr std::array<CharacterStyle,4> masteringStyles{{
    {0,0,0,1.30f,0,0,0.08f,-0.14f}, {0.55f,0,-0.25f,1.45f,3,0.10f,0.15f,-0.48f},
    {0.60f,0.25f,-0.45f,1.85f,-1,0.05f,0.06f,-0.32f}, {-0.45f,0.05f,0.35f,1.18f,1,0,0.48f,-0.10f}
}};
using EQTriplet = std::array<float, 3>;
std::array<Coefficients, 3> eqSections(double rate, const EQTriplet& hz, const EQTriplet& gains);

// Half-octave output band levels. The meter runs only while a reader is polling.
inline constexpr std::array<float, 19> spectrumHz{31.5f, 45, 63, 90, 125, 180, 250, 355, 500,
    710, 1000, 1400, 2000, 2800, 4000, 5600, 8000, 11200, 16000};
using Spectrum = std::array<float, spectrumHz.size()>;
class OutputSpectrum {
    std::array<Coefficients, spectrumHz.size()> coefficients{};
    std::array<std::array<Biquad, spectrumHz.size()>, 2> state{};
    std::array<double, spectrumHz.size()> power{};
    Spectrum shown{};
    Publication<spectrumHz.size()> publication;
    std::atomic<bool> requested{false};
    unsigned interval = 4800, measured = 0, bands = 0, remaining = 0, channels = 2;
public:
    OutputSpectrum() { clear(); }
    void prepare(double rate, unsigned channelCount);
    void clear();
    bool beginBlock(bool offline);
    void push(float left, float right);
    Spectrum read();
};

class Loudness {
    static constexpr int bins = 1001;
    std::array<double, bins> energy{};
    std::array<uint32_t, bins> count{};
    std::array<double, 30> recent{};
    double chunk = 0, shortSum = 0;
    float momentaryLU = -100;
    int hop = 4800, samples = 0, position = 0, recentCount = 0;
    bool newBlock = false;
public:
    void prepare(double rate);
    void reset();
    void restartWindows();
    bool push(double power);
    float integrated() const;
    double shortPower() const;
    float momentary() const { return momentaryLU; }
    bool shortReady() const { return recentCount == 30; }
};

class LoudnessRange {
    // Tenth-LU quantization of 3 s short-term readings sampled every 100 ms.
    std::array<uint64_t, 1001> histogram{};
    double energy = 0;
    uint64_t count = 0;
public:
    float update(double shortPower);
};

// The audition path always tracks input and output power, independent of the meter transport.
class AuditionPower {
    using Pair = std::array<double, 2>;
    std::array<Pair, 30> history{};
    Pair sum{}, chunk{};
    unsigned hop = 4800, samples = 0, pos = 0, filled = 0;
public:
    void prepare(double rate) { *this = {}; hop = unsigned(std::lround(rate / 10)); }
    bool push(double in, double out);
    float difference() const;
};

class Analyzer {
    Loudness loudnessMeter;
    std::array<Coefficients, 6> coefficients;
    std::array<std::array<Biquad, 6>, 2> filters{};
    std::array<double, 6> bandEnergy{};
    double full = 0, mid = 0, side = 0, activeEnergy = 0;
    double rate = 48000;
    float peak = 0;
    unsigned channels = 2;
    uint64_t activeFrames = 0;
public:
    void prepare(double sampleRate, unsigned channelCount);
    void reset();
    bool push(float left, float right, double weightedEnergy);
    std::array<float, profileSize + 2> result() const;
};

struct PeakKernel {
    static constexpr unsigned taps = 24;
    static constexpr unsigned midpoint = taps / 2 - 1;
    std::array<std::array<float, taps>, 3> phase{};
    void prepare();
};
class PeakDetector {
    std::array<std::array<float, PeakKernel::taps * 2>, 2> history{};
    unsigned writeIndex = 0;
public:
    float push(float left, float right, const PeakKernel& kernel);
};

class Processor {
    static constexpr unsigned ringSize = 2048;
    static constexpr unsigned mask = ringSize - 1;
    using Frame = std::array<float, 2>;
    std::array<Frame, ringSize> wetDelay{}, dryDelay{};
    std::array<uint64_t, ringSize> peakPositions{};
    std::array<float, ringSize> peakValues{};
    uint64_t frame = 0;
    unsigned head = 0, end = 0, delay = 0, channels = 2, controlStep = 0;
    double rate = 48000;
    PeakKernel peakKernel;
    PeakDetector limiterDetector, outputDetector;
    float limiterGain = 1, compressorEnvelope = 0, compressorGain = 1;
    float peakHold = 0, blockReduction = 0, mix = 0, dryTrim = 1, wetTrim = 1;
    float corrLL = 0, corrRR = 0, corrLR = 0;
    float release = 0, fast = 0, slow = 0, transition = 0, levelHold = 0;
    std::array<Biquad, 2> bodyFilters{};
    Coefficients bodySection;
    float smoothBody = 0;
    double programmePower = 0;
    float programmeGain = 1, programmeTarget = 1;
    float smoothDrive = 1, smoothWidth = 1, smoothColor = 0, smoothExciter = 0;
    std::array<float, 3> smoothEQ{};
    std::array<Coefficients, 3> eqCoefficients{};
    std::array<std::array<Biquad, 4>, 2> masterFilters{};
    EQTriplet manualGain{}, manualHz{};
    std::array<Coefficients, 3> manualCoefficients{};
    std::array<std::array<Biquad, 3>, 2> manualFilters{};
    bool manualActive = false;
    std::array<std::array<Biquad, 2>, 2> inputK{}, outputK{};
    Coefficients kShelf, kHighPass, exciteFilter, presenceExciter;
    Loudness inputMeter, outputMeter;
    LoudnessRange outputRange;
    AuditionPower auditionPower;
    Analyzer analyzer;
    CalibrationSampler sampler;
    Calibration calibration{};
    using RenderState = std::array<float,profileSize + Calibration{}.size()>;
    Publication<RenderState{}.size()> publishedState;
    RenderState latestState{};
    uint32_t seenCapture = 0, seenReset = 0;
    bool controlsReady = false, lastMetersRunning = true;
    float inputIntegrated = -100, outputIntegrated = -100, currentCorrelation = 0, matchDifference = 0;
    double weighted(Frame signal, std::array<std::array<Biquad, 2>, 2>& state);
    void resetMeters();
public:
    bool modern() const { return calibration[0] == 1; }
    void publish(const Profile& analysis, const Calibration& curve);
    Calibration calibrate(const Profile& analysis, float bodyGain, uint32_t generation, double sampleRate, unsigned channelCount,
                          const std::array<float,parameterCount>& values);
    OutputSpectrum spectrum;
    Publication<profileSize + 3> captured;
    Publication<7> levels;
    Publication<2> extendedLevels;
    std::atomic<bool> metersRunning{true};
    std::atomic<uint32_t> meterEpoch{0};
    std::atomic<uint32_t> captureToken{0}, meterToken{0};
    std::atomic<bool> dry{false}, match{false};
    Profile profile = emptyProfile;
    void prepare(double sampleRate, unsigned channelCount, bool enableCapture = true);
    void reset();
    void render(const float* const* in, float* const* out, unsigned stride, unsigned count,
                const std::array<float, parameterCount>& values, bool hostBypass, bool offline);
    static unsigned latencyFrames(double sampleRate) { return unsigned(std::ceil(sampleRate * 0.003)) + PeakKernel::midpoint; }
};
}

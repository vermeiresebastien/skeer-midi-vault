#pragma once

#include <juce_audio_basics/juce_audio_basics.h>

#include <vector>

namespace vault
{

/** What the host said about its transport, reduced to what a clip can act on. The processor builds
    one from AudioPlayHead::PositionInfo; the emitter takes it as an argument, which is what lets
    the clock be tested without a host running anywhere. */
struct ClipTransport
{
    /** False when the host gave no position at all. Nothing is then emitted -- see process(). */
    bool hasPosition = false;
    bool isPlaying   = false;

    /** The play position in quarter-note beats (VST3's "ppq position"). */
    double beat = 0;

    /** The host tempo. Only used as a divisor when the host reports no position in seconds. */
    double tempoBpm = 120;
};

/** The clip clock: one parsed Standard MIDI File, played against the host's transport.

    This class is where the four behaviours of the plug-in live, and each has one rule:

      * Beat grid. A note's position is its tick divided by the file's ticks-per-quarter-note, and
        with Follow Host Tempo on, one file beat is one host beat. The clip therefore lands on the
        host grid at any tempo, which is the whole reason the library is worth having inside a
        host: the indexed notes are already measured in beats (midivault/engine/analytics.py).
      * Follow off. The clip is then timed in seconds, using the file's own tempo map, so it runs
        at its own speed whatever the host says. The tempo map is piecewise and read from the file,
        including the tie rule the parser uses -- lowest-numbered track wins a tick -- so the
        numbers here and the numbers in the index describe the same performance.
      * Transpose. Semitones, applied to note numbers and to nothing else: velocity, channel,
        timing and every non-note event come out as they came in. A transposition that would leave
        the keyboard drops the note and says so in Report::droppedOutOfRange, because juce::
        MidiMessage::setNoteNumber() clamps to 0..127 silently and a clipped third would be a wrong
        note delivered as though it were the right one.
      * Loop. The clip is as long as its own last played event; on, it repeats from there, off, it
        plays once and stays quiet, which is the same never-wrapping behaviour the app's autoplay
        deck has.

    Meta and sysex never reach the host. The file's tempo and time-signature meta would fight the
    host's own map the moment it is played, and load-time counts them so the browser can say in
    step 7 what a file carried that is not going to be heard from it. */
class MidiEmitter
{
public:
    struct Options
    {
        bool followHostTempo = true;
        bool loop            = true;
        int  transpose       = 0;
    };

    struct Report
    {
        int keyDowns = 0, keyUps = 0, controllers = 0, programs = 0;

        /** Note messages not emitted because transposing them left 0..127. Both halves of a
            dropped note are counted, so key-downs and key-ups stay balanced. */
        int droppedOutOfRange = 0;

        /** True when this block crossed the end of the clip into another cycle. */
        bool wrapped = false;

        /** True when this block closed notes that were still sounding, because the transport
            stopped or jumped backwards. */
        bool flushed = false;
    };

    /** Flattens every track of a parsed file into one timed stream. Cheap enough to call whenever
        the selection changes; the audio thread only ever reads the result. */
    void load (const juce::MidiFile& source);
    void clear();

    /** Forget the anchor, so the next block with a transport restarts the clip from its bar one.
        Call after restoring state or swapping files. */
    void reset() noexcept;

    bool loaded() const noexcept          { return ! events.empty(); }
    int  noteCount() const noexcept       { return keyDownEvents; }
    bool hasBeatGrid() const noexcept     { return beatsPerTick > 0; }

    /** True when the file carries no tempo meta at all and 120 BPM was assumed, which is what
        midivault/engine/smf_parser.py does too -- and marks. The GUI has to be able to say it. */
    bool tempoIsAssumed() const noexcept  { return assumedTempo; }

    double clipLengthBeats() const noexcept   { return clipBeats; }
    double clipLengthSeconds() const noexcept { return clipSeconds; }
    double initialTempoBpm() const noexcept   { return initialTempo; }

    int discardedMeta() const noexcept    { return metaDiscarded; }
    int discardedSysEx() const noexcept   { return sysexDiscarded; }

    /** True once a loaded clip has met a transport without a position. It is not an error -- a
        stopped host, or a host that reports nothing -- but the plug-in is silent until it changes,
        and the browser says so rather than looking broken. */
    bool waitingForTransport() const noexcept { return loaded() && ! hasAnchor; }

    /** Emit whatever falls in this block. The buffer is the caller's, and only this clip's events
        are added to it: whatever the host already put in stays exactly where it was. */
    Report process (const ClipTransport&, const Options&, double sampleRate,
                    int startSample, int numSamples, juce::MidiBuffer& output);

private:
    struct Event
    {
        juce::MidiMessage message;
        double beat = 0, seconds = 0;
        int pitch = 0, channel = 0, velocity = 0;
        bool keyDown = false, keyUp = false;
    };

    struct TempoPoint { double tick = 0, seconds = 0, bpm = 120; };

    /** Seconds at a tick, walking the tempo map with a cursor the caller keeps, because load()
        asks for every event in ascending tick order. */
    double secondsAt (double tick, std::size_t& cursor) const;

    std::vector<Event> events;
    std::vector<TempoPoint> tempoMap;

    double beatsPerTick = 0;     // 0 means SMPTE timing: the file has no beat grid
    double secondsPerTick = 0;   // only used when beatsPerTick is 0
    double clipBeats = 0, clipSeconds = 0, initialTempo = 120;
    int keyDownEvents = 0, metaDiscarded = 0, sysexDiscarded = 0;
    bool assumedTempo = false;

    bool hasAnchor = false;
    double anchorBeat = 0, lastBeat = 0;

    struct Sounding { int channel = 0, pitch = 0, velocity = 0; };
    std::vector<Sounding> sounding;

    JUCE_LEAK_DETECTOR (MidiEmitter)
};

} // namespace vault

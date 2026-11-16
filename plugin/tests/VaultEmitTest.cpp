// Playing a clip: the beat grid, the tempo switch, the transpose and the loop, against a transport
// this program writes itself.
//
// Five claims, and each is a number rather than a description.
//
//   1. Where a note lands. With Follow Host Tempo on, one file beat is one host beat at any host
//      tempo, so a note at beat 5 arrives 5 host beats after the anchor whether the host is at 60
//      or at 240. With it off the clip is timed in seconds through the file's own tempo map, so
//      that same note arrives at the same *seconds* whatever the host says -- and the map is
//      piecewise, which a flat-tempo implementation gets wrong by half a second on the fixture
//      used here.
//   2. What a loop repeats and what it never does. Loop on: a clip plays the same number of
//      key-downs in every cycle and every one of them is answered by a key-up. Loop off: one pass
//      and silence, which is the same never-wrapping rule the app's autoplay deck runs on.
//   3. What a transpose touches. Note numbers and nothing else -- velocities, channels, sample
//      positions, controllers and program changes come out identical at +12 and at 0 -- and a note
//      that would leave the keyboard is dropped and counted, never clamped, because
//      juce::MidiMessage::setNoteNumber() clamps on its own and a clamped third is a wrong note
//      delivered as though it were the one that was asked for.
//   4. Nothing the host did not ask for reaches the host. No meta, no sysex: the file's own tempo
//      meta would fight the host's map the moment it played.
//   5. The three controls are wired to that clock, and the file path is saved with them, so a host
//      project comes back with the same clip under the same transpose -- or says why it cannot.
//
// Section 7 then asks the lossless question of the whole shipped library: played once, every file
// gives up exactly the notes it holds, and nothing else. The exact cycle arithmetic lives in
// section 3, where the clip's geometry is written here rather than inherited from a file.

#include <juce_audio_basics/juce_audio_basics.h>
#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_core/juce_core.h>

#include <cmath>
#include <cstdio>
#include <cstring>
#include <utility>
#include <vector>

#include "VaultMIDIProcessor.h"
#include "VaultMidiEmitter.h"
#include "VaultMidiSource.h"

#ifndef SKEER_FIXTURE_DIR
 #error "SKEER_FIXTURE_DIR must point at the repo's fixtures/demo_library"
#endif

namespace
{

constexpr double kRate = 48000.0;

/** Half a second, which at 120 BPM is exactly one beat: every expected offset in this file is an
    integer number of samples, so a check that fails is a wrong note, not a rounding argument. */
constexpr int kBlock = 24000;

int checks = 0, failures = 0;

void check (bool ok, const juce::String& what)
{
    ++checks;

    if (ok)
    {
        std::printf ("pass  %s\n", what.toRawUTF8());
        return;
    }

    ++failures;
    std::printf ("FAIL  %s\n", what.toRawUTF8());
}

void info (const juce::String& what)
{
    std::printf ("info  %s\n", what.toRawUTF8());
}

//==============================================================================
struct Logged
{
    double sample = 0;
    juce::MidiMessage message;
};

struct Run
{
    std::vector<Logged> events;
    int keyDowns = 0, keyUps = 0, dropped = 0, controllers = 0, programs = 0, meta = 0, sysex = 0;
    bool everWrapped = false, everFlushed = false;

    int notesAt (int pitch) const
    {
        int found = 0;

        for (auto& logged : events)
            if (logged.message.isNoteOnOrOff() && logged.message.getNoteNumber() == pitch)
                ++found;

        return found;
    }

    int keyDownsAt (int pitch) const
    {
        int found = 0;

        for (auto& logged : events)
            if (logged.message.isNoteOn() && logged.message.getNoteNumber() == pitch)
                ++found;

        return found;
    }

    long long pitchSum() const
    {
        long long sum = 0;

        for (auto& logged : events)
            if (logged.message.isNoteOnOrOff())
                sum += logged.message.getNoteNumber();

        return sum;
    }

    long long velocitySum() const
    {
        long long sum = 0;

        for (auto& logged : events)
            if (logged.message.isNoteOn())
                sum += logged.message.getVelocity();

        return sum;
    }

    /** The host's beat at which each event arrived, so two runs at different tempos can be
        compared in the one unit that means something for both. */
    double beatOf (const Logged& logged, double hostTempo) const
    {
        return (logged.sample / kRate) * hostTempo / 60.0;
    }
};

/** Drive one clip from startBeat to endBeat against a transport this function writes, one block at
    a time, and collect everything it put on the wire with absolute sample positions.
    The emitter is built here rather than passed in: a run is one plug-in instance's timeline, and
    the notes it leaves held belong to that instance alone. Reusing an emitter across runs carried
    the previous run's still-sounding notes into the first block of the next one as releases, which
    is real behaviour for a restart but not something a claim about "one cycle of the clip" may
    inherit. */
Run run (const juce::MidiFile& source, const vault::MidiEmitter::Options& options,
         double startBeat, double endBeat, double hostTempo, int blockSize = kBlock)
{
    vault::MidiEmitter emitter;
    emitter.load (source);

    Run outcome;

    const auto beatsPerBlock = (static_cast<double> (blockSize) / kRate) * hostTempo / 60.0;
    juce::MidiBuffer buffer;
    int sampleBase = 0;

    for (int index = 0; startBeat + index * beatsPerBlock < endBeat - 1e-9; ++index)
    {
        buffer.clear();

        vault::ClipTransport transport;
        transport.hasPosition = true;
        transport.isPlaying   = true;
        transport.beat        = startBeat + index * beatsPerBlock;
        transport.tempoBpm    = hostTempo;

        const auto report = emitter.process (transport, options, kRate, 0, blockSize, buffer);

        outcome.keyDowns   += report.keyDowns;
        outcome.keyUps     += report.keyUps;
        outcome.dropped    += report.droppedOutOfRange;
        outcome.controllers += report.controllers;
        outcome.programs   += report.programs;
        outcome.everWrapped = outcome.everWrapped || report.wrapped;
        outcome.everFlushed = outcome.everFlushed || report.flushed;

        for (const auto metadata : buffer)
        {
            outcome.events.push_back ({ static_cast<double> (sampleBase + metadata.samplePosition),
                                        metadata.getMessage() });

            if (metadata.getMessage().isMetaEvent()) ++outcome.meta;
            if (metadata.getMessage().isSysEx())     ++outcome.sysex;
        }

        sampleBase += blockSize;
    }

    return outcome;
}

/** A clip built so that every answer is a round number: 96 ticks to the beat, 120 BPM, a tempo
    change to 60 BPM at bar three, a key-down and its release in the same tick, a velocity-0
    key-down, a controller, a program change, a pitch wheel, sysex and text meta. */
juce::MidiFile makeClip()
{
    juce::MidiFile file;
    file.setTicksPerQuarterNote (96);

    juce::MidiMessageSequence conductor;
    conductor.addEvent (juce::MidiMessage::tempoMetaEvent (500000), 0.0);      // 120 BPM
    conductor.addEvent (juce::MidiMessage::timeSignatureMetaEvent (4, 4), 0.0);
    conductor.addEvent (juce::MidiMessage::textMetaEvent (0x01, "hook starts"), 0.0);
    conductor.addEvent (juce::MidiMessage::tempoMetaEvent (1000000), 384.0);   // 60 BPM at beat 4
    file.addTrack (conductor);

    juce::MidiMessageSequence music;
    music.addEvent (juce::MidiMessage::programChange (1, 3), 0.0);
    music.addEvent (juce::MidiMessage::noteOn (1, 60, static_cast<juce::uint8> (100)), 0.0);
    music.addEvent (juce::MidiMessage::controllerEvent (1, 7, 100), 24.0);
    music.addEvent (juce::MidiMessage::noteOff (1, 60, static_cast<juce::uint8> (0)), 48.0);

    music.addEvent (juce::MidiMessage::pitchWheel (1, 2000), 120.0);
    music.addEvent (juce::MidiMessage::noteOn (2, 64, static_cast<juce::uint8> (90)), 96.0);
    music.addEvent (juce::MidiMessage::noteOff (2, 64, static_cast<juce::uint8> (0)), 192.0);

    // The key-down and its release in the same tick: the case where a buffer that reorders equal
    // timestamps turns a note into a drone.
    music.addEvent (juce::MidiMessage::noteOn (3, 67, static_cast<juce::uint8> (80)), 192.0);
    music.addEvent (juce::MidiMessage::noteOff (3, 67, static_cast<juce::uint8> (0)), 192.0);

    // A velocity-0 key-down is a release wearing a key-down's opcode, and JUCE reads it as one.
    music.addEvent (juce::MidiMessage::noteOn (1, 72, static_cast<juce::uint8> (70)), 288.0);
    music.addEvent (juce::MidiMessage::noteOn (1, 72, static_cast<juce::uint8> (0)), 336.0);

    music.addEvent (juce::MidiMessage::noteOn (4, 63, static_cast<juce::uint8> (60)), 480.0);
    music.addEvent (juce::MidiMessage::noteOff (4, 63, static_cast<juce::uint8> (0)), 576.0);

    const unsigned char sysexBytes[] = { 0xf0, 0x7e, 0x7f, 0x06, 0x01, 0xf7 };
    music.addEvent (juce::MidiMessage (sysexBytes, static_cast<int> (sizeof (sysexBytes))), 0.0);

    file.addTrack (music);

    // A marker a long way past the last note: the clip is as long as its music, not as long as its
    // annotations.
    juce::MidiMessageSequence marks;
    marks.addEvent (juce::MidiMessage::textMetaEvent (0x06, "end"), 4000.0);
    file.addTrack (marks);

    return file;
}

/** Writes a MidiFile over whatever is at that path: replace, not append.

    juce::FileOutputStream opens with OPEN_ALWAYS and seeks to the end of the file on Windows
    (JUCE 8.0.4, juce_core/native/juce_Files_windows.cpp:429-446), so writing a second file to a
    path that already holds one concatenates the two and the result no longer parses. A check that
    swaps the bytes at a saved path has to truncate first, and this is what says so. */
bool replaceFileWith (const juce::File& path, const juce::MidiFile& file)
{
    juce::MemoryOutputStream buffer;

    return file.writeTo (buffer, 1)
           && path.replaceWithData (buffer.getData(), buffer.getDataSize());
}

/** One buffer, resized as needed, for the calls that go through a real processBlock. A MIDI-only
    plugin is still handed an audio buffer by its host, and the block length is read out of it, so
    the check has to supply one. */
juce::AudioBuffer<float>& playBuffer (int numSamples)
{
    static juce::AudioBuffer<float> buffer;
    buffer.setSize (1, numSamples);
    return buffer;
}

//==============================================================================
struct FakeHead : public juce::AudioPlayHead
{
    /** Spelled as a decltype because 8.0.4 returns juce::Optional here and 8.0.9 returns
        std::optional: the override has to match whichever JUCE this build compiles against, and
        both spellings answer to the same calls made below. */
    using Position = decltype (std::declval<const juce::AudioPlayHead&>().getPosition());

    Position getPosition() const override
    {
        if (! reportsPosition)
            return {};

        PositionInfo position;
        position.setPpqPosition (beat);
        position.setBpm (tempo);
        position.setIsPlaying (playing);
        return { position };
    }

    double beat = 0, tempo = 120;
    bool playing = true, reportsPosition = true;
};

juce::String describeParams (VaultMIDIProcessor& processor)
{
    juce::StringArray names;

    for (auto* parameter : processor.getParameters())
        if (parameter != nullptr)
            names.add (parameter->getName (50));

    return names.joinIntoString (", ");
}

int countParam (VaultMIDIProcessor& processor, const juce::String& name)
{
    int found = 0;

    for (auto* parameter : processor.getParameters())
        if (parameter != nullptr && parameter->getName (50).contains (name))
            ++found;

    return found;
}

float paramValue (VaultMIDIProcessor& processor, const juce::String& id)
{
    if (auto* raw = processor.valueTreeState.getRawParameterValue (id))
        return raw->load();

    return -999.0f;
}

/** Move a control the way a host does -- through the parameter -- so the value tree sees it and a
    state saved afterwards carries it. Writing straight to the atomic that getRawParameterValue()
    hands out changes what the audio thread reads but leaves the saved state behind, which is the
    wrong half of the pair to be wrong about. */
void setChoice (VaultMIDIProcessor& processor, const juce::String& id, int index)
{
    if (auto* param = dynamic_cast<juce::AudioParameterChoice*> (processor.valueTreeState.getParameter (id)))
        *param = index;
}

void setInt (VaultMIDIProcessor& processor, const juce::String& id, int value)
{
    if (auto* param = dynamic_cast<juce::AudioParameterInt*> (processor.valueTreeState.getParameter (id)))
        *param = value;
}

} // namespace

//==============================================================================
int main()
{
    juce::Logger::setCurrentLogger (nullptr);

    const vault::MidiEmitter::Options following { true,  true,  0  };
    const vault::MidiEmitter::Options absolute  { false, true,  0  };
    const vault::MidiEmitter::Options onceOnly  { true,  false, 0  };

    //=========================================================================
    // 1. What a parsed file becomes: one timed stream, measured in beats and seconds
    //=========================================================================
    auto clip = makeClip();

    vault::MidiEmitter emitter;
    emitter.load (clip);

    info ("clip: " + juce::String (emitter.noteCount()) + " key-downs, "
          + juce::String (emitter.clipLengthBeats(), 4) + " beats, "
          + juce::String (emitter.clipLengthSeconds(), 4) + " s, opens at "
          + juce::String (emitter.initialTempoBpm(), 1) + " BPM, meta="
          + juce::String (emitter.discardedMeta()) + " sysex="
          + juce::String (emitter.discardedSysEx()));

    check (emitter.loaded() && emitter.noteCount() == 5,
           "the clip has its five key-downs and the velocity-0 one is a release, not a sixth note");

    check (emitter.hasBeatGrid() && ! emitter.tempoIsAssumed()
             && std::abs (emitter.initialTempoBpm() - 120.0) < 1e-9,
           "96 ticks to the beat, a tempo the file stated, and 120 BPM taken from it");

    check (std::abs (emitter.clipLengthBeats() - 6.0) < 1e-9
             && std::abs (emitter.clipLengthSeconds() - 4.0) < 1e-9,
           "six beats long, and four seconds of that is the file's own tempo map: two bars at 120 "
           "then two at 60 -- so the clip ends at the last note and not at the marker three pages later");

    check (emitter.discardedMeta() == 5 && emitter.discardedSysEx() == 1,
           "the five meta events and the one sysex are counted where they are dropped");

    {
        juce::MidiFile silent;
        silent.setTicksPerQuarterNote (48);
        juce::MidiMessageSequence only;
        only.addEvent (juce::MidiMessage::noteOn (1, 40, static_cast<juce::uint8> (99)), 0.0);
        only.addEvent (juce::MidiMessage::noteOff (1, 40, static_cast<juce::uint8> (0)), 48.0);
        silent.addTrack (only);

        vault::MidiEmitter noTempo;
        noTempo.load (silent);

        check (noTempo.tempoIsAssumed() && std::abs (noTempo.initialTempoBpm() - 120.0) < 1e-9
                 && std::abs (noTempo.clipLengthSeconds() - 0.5) < 1e-9,
               "a file that never says how fast it is gets 120 BPM, and says that it was assumed -- "
               "the same default and the same honesty midivault/engine/smf_parser.py uses");
    }

    {
        // Two tracks, one tempo value each, both for tick 0. The lowest-numbered track is the one
        // a sequencer wrote the real map into, and the plug-in has to agree with the index about
        // which of them won, or the two describe different performances of one file.
        juce::MidiFile tied;
        tied.setTicksPerQuarterNote (96);

        juce::MidiMessageSequence first;
        first.addEvent (juce::MidiMessage::tempoMetaEvent (500000), 0.0);    // 120
        tied.addTrack (first);

        juce::MidiMessageSequence second;
        second.addEvent (juce::MidiMessage::tempoMetaEvent (461538), 0.0);   // ~130, later in the file
        second.addEvent (juce::MidiMessage::noteOn (1, 60, static_cast<juce::uint8> (100)), 0.0);
        second.addEvent (juce::MidiMessage::noteOff (1, 60, static_cast<juce::uint8> (0)), 192.0);
        tied.addTrack (second);

        vault::MidiEmitter tie;
        tie.load (tied);

        check (std::abs (tie.clipLengthSeconds() - 1.0) < 1e-9,
               "two tracks that both state a tempo for bar one: the lower-numbered one wins, so the "
               "clip is 2 beats at 120 = 1.000 s and not the 0.923 s the other reading would give");
    }

    //=========================================================================
    // 2. Where a note lands -- the beat grid, and what turning it off gives up
    //=========================================================================
    {
        const auto at120 = run (clip, following, 0.0, 8.0, 120.0);
        const auto at60  = run (clip, following, 0.0, 8.0, 60.0);
        const auto at240 = run (clip, following, 0.0, 8.0, 240.0);

        info ("follow on: " + juce::String (static_cast<int> (at120.events.size()))
              + " events in 8 beats at 120, " + juce::String (static_cast<int> (at60.events.size()))
              + " at 60, " + juce::String (static_cast<int> (at240.events.size())) + " at 240");

        bool sameBeats = at120.events.size() == at60.events.size()
                       && at120.events.size() == at240.events.size();

        for (std::size_t i = 0; i < at120.events.size() && i < at60.events.size()
                                  && i < at240.events.size(); ++i)
        {
            const auto a = at120.beatOf (at120.events[i], 120.0);
            const auto b = at120.beatOf (at60.events[i], 60.0);
            const auto c = at120.beatOf (at240.events[i], 240.0);

            if (std::abs (a - b) > 1e-3 || std::abs (a - c) > 1e-3)
                sameBeats = false;
        }

        check (sameBeats && at120.events.size() == 19,
               "following the host at 60, 120 and 240 BPM puts every one of the clip's 19 events in "
               "eight host beats on the same beat of the bar at all three tempos -- the grid is "
               "beats, not seconds");

        const auto first = at120.events.front();
        check (first.sample == 0 && first.message.isProgramChange()
                 && first.message.getProgramChangeNumber() == 3,
               "the program change at bar one arrives at sample 0 of the first block");

        bool found60 = false, found64 = false, found63 = false;

        for (auto& logged : at120.events)
        {
            if (! logged.message.isNoteOn())
                continue;

            if (logged.message.getNoteNumber() == 60 && logged.sample == 0)         found60 = true;
            if (logged.message.getNoteNumber() == 64 && logged.sample == 24000)     found64 = true;
            if (logged.message.getNoteNumber() == 63 && logged.sample == 120000)    found63 = true;
        }

        check (found60 && found64 && found63,
               "beat 0, beat 1 and beat 5 land on samples 0, 24000 and 120000 at 120 BPM -- one "
               "file beat per host beat, and 24000 samples to the beat at this rate");

        // Eight host beats at 120 BPM and four at 60 are the same four seconds of wall clock, which
        // is the only comparison that means anything once the clip has left the host's grid.
        const auto absAt120 = run (clip, absolute, 0.0, 8.0, 120.0);
        const auto absAt60  = run (clip, absolute, 0.0, 4.0, 60.0);

        bool sameSeconds = absAt120.events.size() == absAt60.events.size();

        for (std::size_t i = 0; i < absAt120.events.size() && i < absAt60.events.size(); ++i)
            if (std::abs (absAt120.events[i].sample - absAt60.events[i].sample) > 1.0)
                sameSeconds = false;

        check (sameSeconds && absAt120.events.size() == 12,
               "with the switch off the clip keeps its own seconds: the same 12 events at the same "
               "sample positions when the host says 60 as when it says 120 -- it is no longer on the "
               "host grid, which is exactly what turning it off means");

        bool note63AtThreeSeconds = false;

        for (auto& logged : absAt120.events)
            if (logged.message.isNoteOn() && logged.message.getNoteNumber() == 63
                 && std::abs (logged.sample - 144000.0) <= 1.0)
                note63AtThreeSeconds = true;

        check (note63AtThreeSeconds,
               "and off, the beat-5 note arrives at 3.000 s and not at 2.500 s: the file halves its "
               "tempo at bar three, so a single flat tempo for the whole clip would put it half a "
               "second early");
    }

    //=========================================================================
    // 3. The loop, and the one cycle that must not repeat
    //=========================================================================
    {
        // A window is measured as one pass plus a beat, then two, then three. That shape is not a
        // convenience: the clip's last event is its closing release, which falls at exactly one
        // loop length -- the same instant the next pass strikes its first note. A window that stops
        // there ends with a note still held, so repetition is shown by what each extra pass *adds*
        // rather than by dividing a total.
        const auto oneCycle = run (clip, following, 0.0, 7.0, 120.0);
        const auto twoCycle = run (clip, following, 0.0, 13.0, 120.0);
        const auto three    = run (clip, following, 0.0, 19.0, 120.0);
        const auto once     = run (clip, onceOnly, 0.0, 18.0, 120.0);

        info ("loop on over three cycles: " + juce::String (three.keyDowns) + " key-downs, "
              + juce::String (three.keyUps) + " key-ups, "
              + juce::String (static_cast<int> (three.events.size())) + " events, wrapped="
              + juce::String (three.everWrapped ? "yes" : "no") + "; loop off over a longer span: "
              + juce::String (once.keyDowns) + " key-downs, " + juce::String (once.keyUps)
              + " key-ups, " + juce::String (static_cast<int> (once.events.size())) + " events");

        const auto one = static_cast<int> (oneCycle.events.size());
        const auto two = static_cast<int> (twoCycle.events.size());
        const auto many = static_cast<int> (three.events.size());

        check (one == 17 && two - one == 13 && many - two == 13,
               "every extra pass of the clip adds exactly the clip's own 13 events and nothing else: "
               + juce::String (one) + ", " + juce::String (two - one) + " and "
               + juce::String (many - two) + " for the first, second and third pass of a six-beat "
               "window run one beat longer than it holds");

        check (oneCycle.keyDowns == 6 && twoCycle.keyDowns - oneCycle.keyDowns == 5
                 && three.keyDowns - twoCycle.keyDowns == 5
                 && three.keyUps == three.keyDowns,
               "and five key-downs per pass on top of the one that opens the window at its own end: "
               + juce::String (oneCycle.keyDowns) + ", " + juce::String (twoCycle.keyDowns)
               + " and " + juce::String (three.keyDowns) + " down against "
               + juce::String (three.keyUps) + " up");

        check (three.keyDowns == three.keyUps,
               "every key-down in the three passes is answered by the time the window closes: the "
               "clip cannot leak a held note through a wrap");

        check (three.everWrapped && ! once.everWrapped,
               "the run that wrapped says it wrapped, and the one that did not says it did not");

        check (once.keyDowns == 5 && once.keyUps == 5
                 && static_cast<int> (once.events.size()) == 13,
               "with Loop on Once the clip plays once inside a span long enough for three: "
               + juce::String (once.keyDowns) + " key-downs, " + juce::String (once.keyUps)
               + " key-ups and " + juce::String (static_cast<int> (once.events.size()))
               + " events, which is the app's own never-wrapping deck in another host");

        const auto coarse = run (clip, following, 0.0, 18.9, 120.0);
        const auto fine   = run (clip, following, 0.0, 18.9, 120.0, 137);

        check (fine.keyDowns == coarse.keyDowns && fine.keyUps == coarse.keyUps
                 && fine.events.size() == coarse.events.size()
                 && fine.pitchSum() == coarse.pitchSum()
                 && fine.velocitySum() == coarse.velocitySum(),
               "the same span through blocks of 137 samples -- a block size that shares no factor "
               "with the grid -- gives the same " + juce::String (coarse.keyDowns) + " key-downs, "
               + juce::String (coarse.keyUps) + " key-ups and "
               + juce::String (static_cast<int> (coarse.events.size()))
               + " events as blocks of 24000: a note is neither lost in the wrap nor fired twice "
               "by a block boundary");

        int doubled = 0;

        for (std::size_t i = 1; i < fine.events.size(); ++i)
            if (fine.events[i].sample == fine.events[i - 1].sample
                 && fine.events[i].message.getRawDataSize() == fine.events[i - 1].message.getRawDataSize()
                 && std::memcmp (fine.events[i].message.getRawData(),
                                 fine.events[i - 1].message.getRawData(),
                                 fine.events[i].message.getRawDataSize()) == 0)
                ++doubled;

        check (doubled == 0,
               "and no two identical messages arrive in the same sample, so nothing fires twice "
               "because a block boundary fell inside one tick");
    }

    //=========================================================================
    // 4. The transpose: what it moves, and what it refuses to invent
    //=========================================================================
    {
        const auto flat     = run (clip, following, 0.25, 6.25, 120.0);
        const auto upTwelve = run (clip, { true, true, 12 }, 0.25, 6.25, 120.0);

        bool shifted = flat.events.size() == upTwelve.events.size();

        for (std::size_t i = 0; i < flat.events.size() && shifted; ++i)
        {
            const auto& a = flat.events[i].message;
            const auto& b = upTwelve.events[i].message;

            if (flat.events[i].sample != upTwelve.events[i].sample)
                shifted = false;
            else if (a.isNoteOnOrOff() && b.isNoteOnOrOff())
            {
                if (b.getNoteNumber() != a.getNoteNumber() + 12
                     || b.getChannel() != a.getChannel()
                     || b.isNoteOn() != a.isNoteOn())
                    shifted = false;
            }
            else if (! b.isNoteOnOrOff())
            {
                if (b.getRawDataSize() != a.getRawDataSize()
                     || std::memcmp (b.getRawData(), a.getRawData(), a.getRawDataSize()) != 0)
                    shifted = false;
            }
            else
                shifted = false;
        }

        info ("transpose 0: " + juce::String (static_cast<int> (flat.events.size()))
              + " events, " + juce::String (flat.keyDowns) + " down / " + juce::String (flat.keyUps)
              + " up, pitches " + juce::String (flat.pitchSum()) + ", velocities "
              + juce::String (flat.velocitySum()) + "; +12 pitches "
              + juce::String (upTwelve.pitchSum()));

        check (shifted,
               "+12 moves twelve semitones onto every note number and nothing else at all: same "
               "count, same samples, same channels, and the controller, program change and pitch "
               "wheel are byte for byte the messages that came out at 0");

        check (upTwelve.pitchSum() == flat.pitchSum()
                 + 12 * (flat.keyDowns + flat.keyUps)
                 && upTwelve.velocitySum() == flat.velocitySum(),
               "and the arithmetic is exactly twelve semitones times every one of the "
               + juce::String (flat.keyDowns + flat.keyUps) + " note messages of one pass, with all "
               + juce::String (flat.velocitySum()) + " of the velocity untouched: "
               + juce::String (flat.pitchSum()) + " to " + juce::String (upTwelve.pitchSum()));

        // 72 + 56 = 128. setNoteNumber() would have sent 127 and reported success.
        const auto upFiftySix = run (clip, { true, true, 56 }, 0.25, 6.25, 120.0);

        check (upFiftySix.dropped == 2 && upFiftySix.keyDowns == 4 && upFiftySix.keyUps == 3
                 && upFiftySix.notesAt (127) == 0,
               "a note that would land at 128 is dropped and counted -- both halves of it -- and not "
               "one of the " + juce::String (upFiftySix.keyDowns + upFiftySix.keyUps)
               + " messages that did arrive sits at 127 pretending to be it");

        check (upFiftySix.keyDowns + upFiftySix.keyUps + upFiftySix.dropped
                 == flat.keyDowns + flat.keyUps,
               "the three numbers add back up to the untransposed run: "
               + juce::String (upFiftySix.keyDowns) + " + " + juce::String (upFiftySix.keyUps)
               + " + " + juce::String (upFiftySix.dropped) + " = "
               + juce::String (flat.keyDowns + flat.keyUps));

        const auto downSeventyTwo = run (clip, { true, true, -72 }, 0.25, 6.25, 120.0);

        check (downSeventyTwo.keyDowns == 1 && downSeventyTwo.keyUps == 1
                 && downSeventyTwo.dropped == 7 && downSeventyTwo.keyDownsAt (0) == 1
                 && downSeventyTwo.notesAt (0) == 2,
               "-72 leaves the clip one note: the C5 that becomes C0 is in range and plays, and the "
               "seven messages that would land below 0 are dropped and counted -- so the two notes at "
               "0 are the one note the file wrote and not six clamps pretending to be a bass line");

        check (downSeventyTwo.keyDowns + downSeventyTwo.keyUps + downSeventyTwo.dropped
                 == flat.keyDowns + flat.keyUps,
               "-72 accounts for its notes the same way: "
               + juce::String (downSeventyTwo.keyDowns) + " + "
               + juce::String (downSeventyTwo.keyUps) + " + "
               + juce::String (downSeventyTwo.dropped) + " = "
               + juce::String (flat.keyDowns + flat.keyUps) + " note messages, the same nine that "
               "played untransposed");

        check (flat.meta == 0 && flat.sysex == 0 && upTwelve.meta == 0 && upTwelve.sysex == 0
                 && upFiftySix.meta == 0 && upFiftySix.sysex == 0
                 && downSeventyTwo.meta == 0 && downSeventyTwo.sysex == 0,
               "no meta and no sysex reaches the host at any setting: the file's own tempo map would "
               "have fought the host's the moment it played");
    }

    //=========================================================================
    // 5. Ordering, and the transport doing something other than going forwards
    //=========================================================================
    {
        // The ordering claims in this section rest on one library behaviour, so it is measured here
        // rather than trusted: two messages stamped at the same sample come back out of a
        // MidiBuffer in the order they were added. If a JUCE ever reversed that, a key-down and its
        // release written in one tick would swap, and the reversal would look like a passing test
        // because every count underneath would still be right.
        {
            juce::MidiBuffer probe;
            probe.addEvent (juce::MidiMessage::noteOn (3, 67, static_cast<juce::uint8> (80)), 1000);
            probe.addEvent (juce::MidiMessage::noteOff (3, 67, static_cast<juce::uint8> (0)), 1000);

            int index = 0, previousSample = -1;
            bool firstIsDown = false, secondIsUp = false, sameSample = false;

            for (const auto metadata : probe)
            {
                if (index == 0)  firstIsDown = metadata.getMessage().isNoteOn();
                if (index == 1) { secondIsUp = metadata.getMessage().isNoteOff();
                                  sameSample = metadata.samplePosition == previousSample; }

                previousSample = metadata.samplePosition;
                ++index;
            }

            check (index == 2 && firstIsDown && secondIsUp && sameSample,
                   "juce::MidiBuffer gives back two messages stamped at the same sample in the order "
                   "they were added -- " + juce::String (index) + " messages read out, key-down first: "
                   + juce::String (firstIsDown ? "yes" : "no") + ", same sample: "
                   + juce::String (sameSample ? "yes" : "no"));
        }

        const auto whole = run (clip, following, 0.0, 6.0, 120.0);

        int downIndex = -1, upIndex = -1, position = 0;

        for (auto& logged : whole.events)
        {
            if (logged.message.getNoteNumber() == 67 && logged.message.getChannel() == 3)
            {
                if (logged.message.isNoteOn() && downIndex < 0)  downIndex = position;
                if (logged.message.isNoteOff() && upIndex < 0)   upIndex = position;
            }

            ++position;
        }

        const auto sameTickDown = downIndex >= 0 && upIndex > downIndex;
        const auto oneSampleApart = sameTickDown
            && whole.events[static_cast<std::size_t> (upIndex)].sample
                 == whole.events[static_cast<std::size_t> (downIndex)].sample;

        info ("the same-tick note: key-down at sample "
              + juce::String (sameTickDown ? whole.events[static_cast<std::size_t> (downIndex)].sample : -1.0, 0)
              + ", key-up at "
              + juce::String (sameTickDown ? whole.events[static_cast<std::size_t> (upIndex)].sample : -1.0, 0));

        check (sameTickDown && oneSampleApart,
               "a key-down and its release written in the same tick reach the host in that order at "
               "the same sample: a zero-length note, which is what the file wrote, and not a note "
               "that never ends");

        {
            // The seam: a note held to the exact end of the clip is released at the same instant the
            // next pass strikes it, on the same pitch and channel. Release first is a re-struck note;
            // key-down first is that note switched off the moment it starts.
            juce::MidiFile seam;
            seam.setTicksPerQuarterNote (96);

            juce::MidiMessageSequence pad;
            pad.addEvent (juce::MidiMessage::tempoMetaEvent (500000), 0.0);
            pad.addEvent (juce::MidiMessage::noteOn (1, 60, static_cast<juce::uint8> (100)), 0.0);
            pad.addEvent (juce::MidiMessage::noteOff (1, 60, static_cast<juce::uint8> (0)), 384.0);
            seam.addTrack (pad);

            const auto passes = run (seam, following, 0.0, 9.0, 120.0);

            int releaseThenDown = 0, downThenRelease = 0;

            for (std::size_t i = 1; i < passes.events.size(); ++i)
            {
                const auto& before = passes.events[i - 1].message;
                const auto& after  = passes.events[i].message;

                if (passes.events[i].sample != passes.events[i - 1].sample
                     || before.getNoteNumber() != 60 || after.getNoteNumber() != 60
                     || before.getChannel() != 1 || after.getChannel() != 1)
                    continue;

                if (before.isNoteOff() && after.isNoteOn())   ++releaseThenDown;
                if (before.isNoteOn() && after.isNoteOff())   ++downThenRelease;
            }

            check (releaseThenDown == 2 && downThenRelease == 0,
                   "at each loop seam the release of the pass that just ended arrives before the "
                   "key-down of the one starting, at the same sample: "
                   + juce::String (releaseThenDown) + " seams ordered release-then-down, "
                   + juce::String (downThenRelease) + " the other way, over four beats of a "
                   + juce::String (seam.getNumTracks()) + "-track clip that ends on a held note");
        }

        {
            vault::MidiEmitter waiting;
            waiting.load (clip);

            juce::MidiBuffer buffer;
            vault::ClipTransport blind;
            blind.hasPosition = false;
            blind.isPlaying = true;
            blind.tempoBpm = 120;

            const auto report = waiting.process (blind, following, kRate, 0, kBlock, buffer);

            check (buffer.getNumEvents() == 0 && report.keyDowns == 0
                     && waiting.waitingForTransport(),
                   "a host that reports no position gets silence and a reason: the plug-in does not "
                   "guess where bar one is, because a guess would put the notes somewhere the grid "
                   "is not");
        }

        {
            vault::MidiEmitter mid;
            mid.load (clip);

            juce::MidiBuffer sounding, stopped;
            vault::ClipTransport playing;
            playing.hasPosition = true;
            playing.isPlaying = true;
            playing.tempoBpm = 120;
            playing.beat = 0.0;

            // Two beats: the clip's E4 opens at beat 1 and its release falls at beat 2, which is
            // the next block -- so at this instant the note is genuinely still down.
            mid.process (playing, following, kRate, 0, 2 * kBlock, sounding);

            playing.isPlaying = false;
            const auto report = mid.process (playing, following, kRate, 0, kBlock, stopped);

            int releases = 0;

            for (const auto metadata : stopped)
                if (metadata.getMessage().isNoteOff() && metadata.getMessage().getNoteNumber() == 64)
                    ++releases;

            check (report.flushed && releases == 1 && report.keyUps == 1,
                   "stopping the transport under a note that was still down releases it in the block "
                   "where the transport stopped -- a held oscillator after someone pressed stop is "
                   "not their fault");
        }

        {
            vault::MidiEmitter seek;
            seek.load (clip);

            juce::MidiBuffer before, onwards, jumped;
            vault::ClipTransport playing;
            playing.hasPosition = true;
            playing.isPlaying = true;
            playing.tempoBpm = 120;
            playing.beat = 2.0;

            seek.process (playing, following, kRate, 0, kBlock, before);   // anchors at beat 2

            playing.beat = 10.0;                                           // a jump forwards is not a seek
            seek.process (playing, following, kRate, 0, kBlock, onwards);

            int fromBarOne = 0, fromBeatTwo = 0;

            for (const auto metadata : onwards)
            {
                const auto& message = metadata.getMessage();

                // Eight host beats past the anchor is the clip's own beat 8, which is its beat 2 --
                // so this block is the E4 release, the G3 note written on the very same tick, and
                // that G3's release. What must not be here is anything from the clip's bar one.
                if (message.isProgramChange()
                     || (message.isNoteOn() && message.getNoteNumber() == 60))
                    ++fromBarOne;

                if (message.isNoteOn() && message.getNoteNumber() == 67)
                    ++fromBeatTwo;
            }

            playing.beat = 0.0;                                            // the host loop coming back
            seek.process (playing, following, kRate, 0, kBlock, jumped);

            int restarts = 0;

            for (const auto metadata : jumped)
                if (metadata.getMessage().isNoteOn() && metadata.getMessage().getNoteNumber() == 60
                     && metadata.samplePosition == 0)
                    ++restarts;

            check (fromBarOne == 0 && fromBeatTwo == 1 && restarts == 1,
                   "a jump forwards is not a restart: eight host beats past an anchor at beat 2 "
                   "lands on the clip's own beat 2, so the G3 of that tick plays and nothing from "
                   "bar one does -- and when the host comes back to its own bar one, the clip does "
                   "too");
        }
    }

    //=========================================================================
    // 6. The three controls, the play head, and what a saved project gets back
    //=========================================================================
    {
        const auto sandbox = juce::File::getSpecialLocation (juce::File::currentExecutableFile)
                                 .getParentDirectory().getChildFile ("midivault-emit-sandbox");

        sandbox.deleteRecursively();

        if (! sandbox.createDirectory())
        {
            std::printf ("FAIL  the sandbox beside the exe could not be created: %s\n",
                         sandbox.getFullPathName().toRawUTF8());
            return 1;
        }

        const auto clipPath = sandbox.getChildFile ("hook.mid");
        {
            juce::FileOutputStream writer (clipPath);

            if (! writer.openedOk() || ! clip.writeTo (writer, 1))
            {
                std::printf ("FAIL  the clip could not be written to %s\n",
                             clipPath.getFullPathName().toRawUTF8());
                return 1;
            }
        }

        VaultMIDIProcessor processor;
        FakeHead head;

        processor.setPlayHead (&head);
        processor.setRateAndBufferSizeDetails (kRate, kBlock);
        processor.prepareToPlay (kRate, kBlock);

        const bool loaded = processor.loadFile (clipPath.getFullPathName());
        const auto clipStatus = processor.status();

        info ("processor: loaded=" + juce::String (loaded ? "yes" : "no") + ", "
              + juce::String (clipStatus.notes) + " notes, " + juce::String (clipStatus.bytesOnDisk)
              + " bytes, digest " + clipStatus.contentHash.substring (0, 12) + "..., params: "
              + describeParams (processor));

        check (loaded && clipStatus.loaded && clipStatus.notes == 5
                 && clipStatus.bytesOnDisk > 0 && clipStatus.contentHash.length() == 64,
               "loadFile puts the clip on the clock and keeps the digest of the bytes it read, which "
               "is what step 7 compares against the index row");

        check (clipStatus.restore == VaultMIDIProcessor::ClipStatus::RestoreCheck::nothingSaved
                 && clipStatus.savedHash.isEmpty() && clipStatus.savedStateVersion == 0,
               "a file picked by hand is not a restore: no saved digest exists, so status() claims "
               "nothing about bytes nobody recorded");

        check (countParam (processor, "Follow") == 1 && countParam (processor, "Transpose") == 1
                 && countParam (processor, "Loop") == 1 && processor.getParameters().size() == 3,
               "the processor owns exactly three parameters: " + describeParams (processor));

        check (paramValue (processor, VaultMIDIProcessor::followTempoId) >= 0.5f
                 && paramValue (processor, VaultMIDIProcessor::loopId) >= 0.5f
                 && paramValue (processor, VaultMIDIProcessor::transposeId) == 0.0f,
               "and they come up on the useful defaults: following the host, looping, in tune");

        {
            juce::MidiBuffer buffer;
            head.beat = 0;
            head.tempo = 120;
            head.playing = true;
            processor.processBlock (playBuffer (kBlock), buffer);

            int downs = 0;

            for (const auto metadata : buffer)
                if (metadata.getMessage().isNoteOn())
                    ++downs;

            check (downs > 0, "the first block of a run plays notes through the real processBlock");
        }

        {
            // A host with no audio bus hands over a buffer with no channels, and therefore no
            // frames. The clip still needs a window, and prepareToPlay said how wide it is.
            processor.prepareToPlay (kRate, kBlock);

            juce::AudioBuffer<float> empty (0, 0);
            juce::MidiBuffer buffer;
            head.beat = 0;
            processor.processBlock (empty, buffer);

            int downs = 0;
            bool inside = buffer.getNumEvents() > 0;

            for (const auto metadata : buffer)
            {
                if (metadata.getMessage().isNoteOn()) ++downs;
                if (metadata.samplePosition < 0 || metadata.samplePosition >= kBlock)
                    inside = false;
            }

            check (downs > 0 && inside,
                   "a zero-length audio buffer does not silence the clip: the block size the host "
                   "gave in prepareToPlay is the fallback, and every event stays inside it");
        }

        {
            processor.prepareToPlay (kRate, kBlock);
            setInt (processor, VaultMIDIProcessor::transposeId, 12);

            juce::MidiBuffer buffer;
            head.beat = 0;
            processor.processBlock (playBuffer (kBlock), buffer);

            int downs = 0;
            bool moved = buffer.getNumEvents() > 0;

            for (const auto metadata : buffer)
                if (metadata.getMessage().isNoteOn())
                {
                    ++downs;
                    moved = moved && metadata.getMessage().getNoteNumber() >= 72;
                }

            check (moved && downs > 0,
                   "the Transpose knob reaches the wire: every key-down in the block is a C or "
                   "higher, because this clip opens on C4 and the host is being followed");

            setInt (processor, VaultMIDIProcessor::transposeId, 0);
        }

        {
            // 121 BPM: one block is 1.00833 host beats, so on the grid the clip's beat-1 note falls
            // inside it; off the grid the same block is 0.5 s, which is exactly where that note sits
            // and therefore outside it. The two settings cannot agree, and that is the claim.
            processor.prepareToPlay (kRate, kBlock);
            setChoice (processor, VaultMIDIProcessor::followTempoId, 1);
            head.tempo = 121;
            head.beat = 0;

            juce::MidiBuffer onGrid;
            processor.processBlock (playBuffer (kBlock), onGrid);

            int downsOn = 0;
            double lastOn = -1;

            for (const auto metadata : onGrid)
                if (metadata.getMessage().isNoteOn())
                {
                    ++downsOn;
                    lastOn = metadata.samplePosition;
                }

            processor.prepareToPlay (kRate, kBlock);
            setChoice (processor, VaultMIDIProcessor::followTempoId, 0);

            juce::MidiBuffer offGrid;
            processor.processBlock (playBuffer (kBlock), offGrid);

            int downsOff = 0;

            for (const auto metadata : offGrid)
                if (metadata.getMessage().isNoteOn())
                    ++downsOff;

            // 60/121 s to the beat at this tempo = 23801.65 samples; the emitter truncates.
            check (downsOn == 2 && lastOn >= 23790 && lastOn <= 23810 && downsOff == 1,
                   "the switch reaches the wire: at a 121 BPM host one block holds two key-downs on "
                   "the grid, the second at sample " + juce::String (static_cast<int> (lastOn))
                   + " where 23801 is the beat, and one key-down off it");

            setChoice (processor, VaultMIDIProcessor::followTempoId, 1);
            head.tempo = 120;
        }

        {
            setInt (processor, VaultMIDIProcessor::transposeId, 7);
            setChoice (processor, VaultMIDIProcessor::followTempoId, 0);

            juce::MemoryBlock state;
            processor.getStateInformation (state);

            VaultMIDIProcessor restored;
            restored.setStateInformation (state.getData(), static_cast<int> (state.getSize()));

            const auto back = restored.status();

            check (back.loaded && back.notes == 5 && back.file == clipPath.getFullPathName()
                     && back.savedFile == back.file
                     && paramValue (restored, VaultMIDIProcessor::transposeId) == 7.0f
                     && paramValue (restored, VaultMIDIProcessor::followTempoId) < 0.5f,
                   "a host's saved state comes back with the same clip, the same transpose and the "
                   "switch in the same place -- the arrangement it saved is the one it gets");

            check (back.restore == VaultMIDIProcessor::ClipStatus::RestoreCheck::matches
                     && back.savedHash == back.contentHash && back.contentHash.length() == 64
                     && back.savedStateVersion == 2,
                   "and returning to untouched bytes is reported as a match: the state recorded "
                   "version " + juce::String (back.savedStateVersion) + " and digest "
                   + back.savedHash.substring (0, 12) + "..., which is what is on disk now");

            setInt (processor, VaultMIDIProcessor::transposeId, 0);
            setChoice (processor, VaultMIDIProcessor::followTempoId, 1);
        }

        {
            // The project was saved against these bytes and the file under that name was replaced
            // since. The clip still plays what is there now -- the user is authoritative about
            // what should be heard -- but status() has to say the bytes are not the project's.
            juce::MemoryBlock savedState;
            processor.getStateInformation (savedState);

            const auto projectHash = processor.status().contentHash;

            juce::MidiFile replacement;
            replacement.setTicksPerQuarterNote (96);
            juce::MidiMessageSequence notes;
            notes.addEvent (juce::MidiMessage::noteOn (1, 48, static_cast<juce::uint8> (100)), 0.0);
            notes.addEvent (juce::MidiMessage::noteOff (1, 48, static_cast<juce::uint8> (0)), 96.0);
            replacement.addTrack (notes);

            check (replaceFileWith (clipPath, replacement),
                   "the fixture at the saved path can be swapped for a different MIDI file");

            VaultMIDIProcessor restored;
            restored.setStateInformation (savedState.getData(),
                                          static_cast<int> (savedState.getSize()));

            const auto back = restored.status();

            check (back.loaded && back.notes == 1
                     && back.restore == VaultMIDIProcessor::ClipStatus::RestoreCheck::differs
                     && back.savedHash == projectHash && back.contentHash != projectHash,
                   "a file edited under a saved path is disclosed rather than refused: the clip "
                   "loads (" + juce::String (back.notes) + " note), the project's digest "
                   + back.savedHash.substring (0, 12) + "... is kept beside the one on disk "
                   + back.contentHash.substring (0, 12) + "..., and neither is silently treated as "
                   "the other");

            // Put the original bytes back: every check after this one plays this clip.
            check (replaceFileWith (clipPath, clip),
                   "and the original fixture is restored for the checks that follow");
        }

        {
            // A project whose file is gone: silent, but naming the path and the digest it wanted
            // instead of quietly starting over with no clip.
            const auto gonePath = sandbox.getChildFile ("gone.mid");

            {
                juce::FileOutputStream writer (gonePath);
                check (writer.openedOk() && clip.writeTo (writer, 1),
                       "the file a doomed project points at can be written");
            }

            VaultMIDIProcessor doomed;
            doomed.loadFile (gonePath.getFullPathName());

            juce::MemoryBlock savedState;
            doomed.getStateInformation (savedState);

            const auto projectHash = doomed.status().contentHash;

            check (gonePath.deleteFile(), "and deleted after the project was saved");

            VaultMIDIProcessor restored;
            restored.setStateInformation (savedState.getData(),
                                          static_cast<int> (savedState.getSize()));

            const auto back = restored.status();

            check (! back.loaded && back.restore == VaultMIDIProcessor::ClipStatus::RestoreCheck::missing
                     && back.savedHash == projectHash && back.error.isNotEmpty(),
                   "a project whose file is gone comes back silent with the digest it wanted "
                   "(" + back.savedHash.substring (0, 12) + "...) and the reason on it: "
                   + back.error.substring (0, 40));
        }

        {
            // Every project saved before this change: the same tree without the two new keys. It
            // has to keep restoring, and make no claim about bytes nobody recorded.
            juce::MemoryBlock current;
            processor.getStateInformation (current);

            std::unique_ptr<juce::XmlElement> legacy (
                juce::AudioProcessor::getXmlFromBinary (current.getData(),
                                                        static_cast<int> (current.getSize())));

            check (legacy != nullptr && legacy->hasAttribute ("sourceHash")
                     && legacy->hasAttribute ("stateVersion"),
                   "today's state carries the digest and the version that make the next check a "
                   "real older shape rather than a guess");

            juce::MemoryBlock oldBlob;

            if (legacy != nullptr)
            {
                legacy->removeAttribute ("sourceHash");
                legacy->removeAttribute ("stateVersion");
                juce::AudioProcessor::copyXmlToBinary (*legacy, oldBlob);
            }

            VaultMIDIProcessor restored;
            restored.setStateInformation (oldBlob.getData(), static_cast<int> (oldBlob.getSize()));

            const auto back = restored.status();

            check (back.loaded && back.notes == 5 && back.file == clipPath.getFullPathName()
                     && back.restore == VaultMIDIProcessor::ClipStatus::RestoreCheck::nothingSaved
                     && back.savedHash.isEmpty() && back.savedStateVersion == 0,
                   "a project saved before the hash key existed still restores and plays its clip, "
                   "and is not accused of changing: nothing was recorded, so nothing is claimed");
        }

        {
            // The preset switch. A session is playing file A when the host loads a project that names
            // a file B which is not there. The tree now says B while the clip in memory is still A,
            // and the next save is where the two authorities used to be welded together: without an
            // agreement check the blob would carry B's path under A's digest and version 2, and the
            // session after that would accuse an untouched B of changing.
            const auto absentPath = sandbox.getChildFile ("absent.mid").getFullPathName();

            VaultMIDIProcessor session;
            session.setRateAndBufferSizeDetails (kRate, kBlock);
            session.prepareToPlay (kRate, kBlock);

            check (session.loadFile (clipPath.getFullPathName())
                     && ! juce::File (absentPath).existsAsFile(),
                   "a session holds file A, and the file the next project names is not on disk");

            juce::MemoryBlock stateOfA;
            session.getStateInformation (stateOfA);

            std::unique_ptr<juce::XmlElement> elementOfA (
                juce::AudioProcessor::getXmlFromBinary (stateOfA.getData(),
                                                        static_cast<int> (stateOfA.getSize())));

            const auto hashA = session.status().contentHash;

            check (elementOfA != nullptr
                     && elementOfA->getStringAttribute ("sourceFile") == clipPath.getFullPathName()
                     && elementOfA->getStringAttribute ("sourceHash") == hashA
                     && elementOfA->getIntAttribute ("stateVersion") == 2,
                   "a project saved while A plays records A's path, A's digest "
                   + hashA.substring (0, 12) + "..., and version 2 beside them");

            juce::MemoryBlock stateOfB;
            const auto digestB = juce::String::repeatedString ("b", 64);

            if (elementOfA != nullptr)
            {
                auto elementOfB = *elementOfA;
                elementOfB.setAttribute ("sourceFile", absentPath);
                elementOfB.setAttribute ("sourceHash", digestB);
                juce::AudioProcessor::copyXmlToBinary (elementOfB, stateOfB);
            }

            session.setStateInformation (stateOfB.getData(), static_cast<int> (stateOfB.getSize()));

            const auto afterFailedRestore = session.status();

            check (! afterFailedRestore.loaded && afterFailedRestore.notes == 0
                     && afterFailedRestore.contentHash.isEmpty()
                     && afterFailedRestore.error.isNotEmpty()
                     && afterFailedRestore.file.isEmpty()
                     && afterFailedRestore.savedFile == absentPath
                     && afterFailedRestore.savedHash == digestB
                     && afterFailedRestore.savedStateVersion == 2
                     && afterFailedRestore.restore
                          == VaultMIDIProcessor::ClipStatus::RestoreCheck::missing,
                   "switching to a project whose file is gone empties the session instead of leaving "
                   "A's clip under B's name: nothing plays, the project's path is still named as the "
                   "file it wants, and B's digest is kept for the browser to show");

            juce::MemoryBlock savedAfter;
            session.getStateInformation (savedAfter);

            std::unique_ptr<juce::XmlElement> elementAfter (
                juce::AudioProcessor::getXmlFromBinary (savedAfter.getData(),
                                                        static_cast<int> (savedAfter.getSize())));

            check (elementAfter != nullptr
                     && elementAfter->getStringAttribute ("sourceFile") == absentPath
                     && ! elementAfter->hasAttribute ("sourceHash")
                     && ! elementAfter->hasAttribute ("stateVersion"),
                   "and saving now keeps the path the project wanted while writing neither digest "
                   "nor version: the blob states intent and claims nothing about bytes it did not "
                   "read");

            {
                // Silent is a stronger claim than "not loaded": a clip left resident would answer
                // the transport with notes that belong to the project the host just left.
                FakeHead silentHead;
                session.setPlayHead (&silentHead);
                session.prepareToPlay (kRate, kBlock);

                int events = 0;

                for (int block = 0; block < 3; ++block)
                {
                    juce::MidiBuffer buffer;
                    silentHead.beat = block;
                    session.processBlock (playBuffer (kBlock), buffer);
                    events += buffer.getNumEvents();
                }

                check (events == 0, "and blocks after the failed restore carry no MIDI at all");
            }

            {
                // Why the path has to survive: the drive comes back. The same blob, restored once
                // the file exists again, has to heal -- and it has no digest to compare against,
                // because the failed restore honestly recorded none.
                check (replaceFileWith (juce::File (absentPath), clip),
                       "the file the project wants is put back where the project says it lives");

                FakeHead healedHead;
                VaultMIDIProcessor reopened;
                reopened.setRateAndBufferSizeDetails (kRate, kBlock);
                reopened.setPlayHead (&healedHead);
                reopened.prepareToPlay (kRate, kBlock);

                reopened.setStateInformation (savedAfter.getData(),
                                              static_cast<int> (savedAfter.getSize()));

                const auto healed = reopened.status();

                check (healed.loaded && healed.notes == 5 && healed.error.isEmpty()
                         && healed.file == absentPath && healed.savedFile == absentPath
                         && healed.restore
                              == VaultMIDIProcessor::ClipStatus::RestoreCheck::nothingSaved
                         && healed.savedHash.isEmpty(),
                       "and the same blob restores and plays once the file is back, with no digest "
                       "recorded and so no accusation: the project heals instead of forgetting its "
                       "clip");

                int events = 0;

                for (int block = 0; block < 3; ++block)
                {
                    juce::MidiBuffer buffer;
                    healedHead.beat = block;
                    reopened.processBlock (playBuffer (kBlock), buffer);
                    events += buffer.getNumEvents();
                }

                check (events > 0, "and the healed clip answers the transport with notes again");
            }
        }

        {
            // The same defect by the other route: a blob that names no file at all. The previous
            // clip has to go, and nothing may be accused of being missing, because nothing was named.
            VaultMIDIProcessor session;
            session.setRateAndBufferSizeDetails (kRate, kBlock);
            session.prepareToPlay (kRate, kBlock);
            session.loadFile (clipPath.getFullPathName());

            juce::MemoryBlock withA;
            session.getStateInformation (withA);

            std::unique_ptr<juce::XmlElement> element (
                juce::AudioProcessor::getXmlFromBinary (withA.getData(),
                                                        static_cast<int> (withA.getSize())));

            juce::MemoryBlock emptyPath;

            if (element != nullptr)
            {
                element->removeAttribute ("sourceFile");
                element->removeAttribute ("sourceHash");
                element->removeAttribute ("stateVersion");
                juce::AudioProcessor::copyXmlToBinary (*element, emptyPath);
            }

            session.setStateInformation (emptyPath.getData(), static_cast<int> (emptyPath.getSize()));

            const auto back = session.status();

            check (! back.loaded && back.notes == 0 && back.contentHash.isEmpty()
                     && back.file.isEmpty() && back.savedFile.isEmpty()
                     && back.restore == VaultMIDIProcessor::ClipStatus::RestoreCheck::nothingSaved,
                   "a project that names no file restores nothing and plays nothing, and does not "
                   "call a file missing that it never named");
        }

        {
            // "Gone" and "there but unreadable" ask the user to do different things, and the source
            // is the only thing that knows which happened -- testing the path again elsewhere would
            // guess, and would report a permission denial as a missing file.
            const juce::File garbage = juce::File (SKEER_FIXTURE_DIR)
                                           .getChildFile ("Misc")
                                           .getChildFile ("Corrupt Second Chunk.mid");

            vault::MidiSource noFile;
            const auto noFileLoaded =
                noFile.load (sandbox.getChildFile ("nowhere.mid").getFullPathName());

            vault::MidiSource notMidi;
            const auto notMidiLoaded = notMidi.load (garbage.getFullPathName());

            check (! noFileLoaded && noFile.failure() == vault::MidiSource::LoadFailure::notFound
                     && ! notMidiLoaded
                     && notMidi.failure() == vault::MidiSource::LoadFailure::unreadable,
                   "the source tells a path with nothing at it from a file that is there and will "
                   "not parse: " + notMidi.errorMessage().substring (0, 40));

            VaultMIDIProcessor session;
            session.setRateAndBufferSizeDetails (kRate, kBlock);
            session.prepareToPlay (kRate, kBlock);
            session.loadFile (clipPath.getFullPathName());

            juce::MemoryBlock withA;
            session.getStateInformation (withA);

            std::unique_ptr<juce::XmlElement> element (
                juce::AudioProcessor::getXmlFromBinary (withA.getData(),
                                                        static_cast<int> (withA.getSize())));

            juce::MemoryBlock stateOfOther;

            if (element != nullptr)
            {
                auto other = *element;
                other.setAttribute ("sourceFile", garbage.getFullPathName());
                juce::AudioProcessor::copyXmlToBinary (other, stateOfOther);
            }

            VaultMIDIProcessor restored;
            restored.setStateInformation (stateOfOther.getData(),
                                          static_cast<int> (stateOfOther.getSize()));

            const auto back = restored.status();

            check (! back.loaded && back.notes == 0 && back.contentHash.isEmpty()
                     && back.error.isNotEmpty()
                     && back.restore
                          == VaultMIDIProcessor::ClipStatus::RestoreCheck::unreadable,
                   "and a project pointing at a file that exists but will not parse is reported as "
                   "unreadable rather than missing: " + back.error.substring (0, 40));
        }

        {
            // unload() is what the editor's eject button will call in step 6. Nothing exercised it.
            VaultMIDIProcessor session;
            session.setRateAndBufferSizeDetails (kRate, kBlock);
            session.prepareToPlay (kRate, kBlock);
            session.loadFile (clipPath.getFullPathName());

            check (session.status().loaded, "a session is playing a clip before it is unloaded");

            session.unload();

            const auto after = session.status();
            const auto& tree = session.valueTreeState.state;

            check (! after.loaded && after.notes == 0 && after.contentHash.isEmpty()
                     && after.file.isEmpty() && after.savedFile.isEmpty()
                     && after.restore == VaultMIDIProcessor::ClipStatus::RestoreCheck::nothingSaved
                     && session.errorMessage().isEmpty(),
                   "unload leaves nothing loaded: no notes, no digest, no path, no complaint");

            check (! tree.hasProperty ("sourceFile") && ! tree.hasProperty ("sourceHash")
                     && ! tree.hasProperty ("stateVersion"),
                   "and takes the three keys off the live tree rather than leaving a path the next "
                   "save would carry");

            juce::MemoryBlock savedAfter;
            session.getStateInformation (savedAfter);

            std::unique_ptr<juce::XmlElement> xml (
                juce::AudioProcessor::getXmlFromBinary (savedAfter.getData(),
                                                        static_cast<int> (savedAfter.getSize())));

            check (xml != nullptr && ! xml->hasAttribute ("sourceHash")
                     && ! xml->hasAttribute ("stateVersion"),
                   "a project saved after an eject records no digest and no version");
        }

        {
            // A path that names nothing must not be replaced by something else to keep the plug-in
            // looking alive.
            const auto gonePath = sandbox.getChildFile ("later.mid").getFullPathName();

            VaultMIDIProcessor missing;
            missing.loadFile (gonePath);   // fails: nothing was ever written there

            const auto after = missing.status();

            check (! after.loaded && after.error.isNotEmpty() && after.file.isEmpty(),
                   "a path that does not exist leaves the plug-in silent with the reason on it: "
                   + after.error.substring (0, 40));

            check (! missing.loadFile (clipPath.getFullPathName().dropLastCharacters (1)),
                   "and a truncated path is refused rather than guessed at");

            check (missing.loadFile (clipPath.getFullPathName()) && missing.status().loaded,
                   "the same processor plays the clip as soon as it is pointed at a file that exists");
        }

        {
            // A clip whose source is replaced by the corrupt file the library ships: the load that
            // fails has to leave the one already playing alone.
            const juce::File garbage = juce::File (SKEER_FIXTURE_DIR)
                                           .getChildFile ("Misc")
                                           .getChildFile ("Corrupt Second Chunk.mid");

            const auto good = processor.loadFile (clipPath.getFullPathName());
            const auto bad = processor.loadFile (garbage.getFullPathName());

            check (garbage.existsAsFile(), "the library's damaged fixture is where this check says it is");
            check (good && ! bad && processor.status().loaded && processor.status().notes == 5
                     && processor.status().file == clipPath.getFullPathName()
                     && processor.errorMessage().isNotEmpty(),
                   "a file that cannot be read does not stop the audition or steal the slot: the "
                   "clip that was playing keeps playing, and the error is there to be shown -- "
                   + processor.errorMessage().substring (0, 40));
        }

        sandbox.deleteRecursively();
    }

    //=========================================================================
    // 7. Every file the repo ships, played once
    //
    // Misc/ is the app's own adversarial set, so the claim is not "all of them parse". It is that
    // every file that does parse gives up exactly the notes it holds -- the same losslessness the
    // index was built on, now measured at the wire instead of in the parser -- and that the ones
    // meant as damage are refused on the way in.
    //=========================================================================
    {
        const juce::File library (SKEER_FIXTURE_DIR);
        const auto files = library.findChildFiles (juce::File::findFiles, true, "*.mid");

        int played = 0, refused = 0;
        juce::StringArray leaks, wrongCount, altered, tooShort, smpteNamed, refusedNames;
        double longestSeconds = 0;

        for (const auto& file : files)
        {
            vault::MidiSource source;

            if (! source.load (file.getFullPathName()))
            {
                ++refused;
                refusedNames.add (file.getFileName());
                continue;
            }

            vault::MidiEmitter player;
            player.load (source.midiFile());

            const auto name = file.getFileName();

            if (! player.loaded())
            {
                ++refused;
                refusedNames.add (name + " (parsed, but nothing playable in it)");
                continue;
            }

            int fileDowns = 0, fileUps = 0;
            long long filePitches = 0, fileVelocities = 0;

            for (int t = 0; t < source.numTracks(); ++t)
            {
                const auto* track = source.track (t);

                for (int i = 0; track != nullptr && i < track->getNumEvents(); ++i)
                {
                    const auto& message = track->getEventPointer (i)->message;

                    if (message.isNoteOn())
                    {
                        ++fileDowns;
                        filePitches    += message.getNoteNumber();
                        fileVelocities += message.getVelocity();
                    }
                    else if (message.isNoteOff())
                    {
                        ++fileUps;
                        filePitches += message.getNoteNumber();
                    }
                }
            }

            ++played;
            longestSeconds = juce::jmax (longestSeconds, player.clipLengthSeconds());

            if (! (player.clipLengthBeats() > 0 || player.clipLengthSeconds() > 0))
            {
                tooShort.add (name + " (" + juce::String (fileDowns)
                              + " key-downs, all of them at tick 0, so there is no length to play "
                              "through)");
                continue;
            }

            // One pass, no loop, and half a beat of slack so an event sitting exactly on the end of
            // the clip falls inside the window rather than on its edge. A file with a beat grid is
            // run in beats; a SMPTE file has none, and at 120 BPM the host's beat is half a second.
            const auto endBeat = player.hasBeatGrid() ? player.clipLengthBeats() + 0.5
                                                      : (player.clipLengthSeconds() + 0.25) * 2.0;

            const auto pass = run (source.midiFile(), onceOnly, 0.0, endBeat, 120.0);

            if (pass.keyDowns != fileDowns || pass.keyUps != fileUps)
                wrongCount.add (name + " (" + juce::String (fileDowns) + "/" + juce::String (fileUps)
                                + " in the file -> " + juce::String (pass.keyDowns) + " down / "
                                + juce::String (pass.keyUps) + " up out)");

            if (pass.pitchSum() != filePitches)
                altered.add (name + " (pitches " + juce::String (pass.pitchSum()) + " out vs "
                             + juce::String (filePitches) + " in)");

            if (pass.velocitySum() != fileVelocities)
                altered.add (name + " (velocities " + juce::String (pass.velocitySum()) + " out vs "
                             + juce::String (fileVelocities) + " in)");

            if (pass.meta != 0 || pass.sysex != 0)
                leaks.add (name + " (" + juce::String (pass.meta) + " meta, "
                           + juce::String (pass.sysex) + " sysex)");

            if (! player.hasBeatGrid())
                smpteNamed.add (name + " (" + juce::String (player.clipLengthSeconds(), 2) + " s)");
        }

        info ("played " + juce::String (played) + " of " + juce::String (files.size())
              + " library files once through; longest clip "
              + juce::String (longestSeconds, 2) + " s");

        check (files.size() >= 30 && played >= 25,
               "the library is where the repo says it is -- " + juce::String (files.size())
               + " files, " + juce::String (played) + " of them clips a transport can play");

        check (tooShort.isEmpty(), "every playable file has a length to play through, so one pass "
               "can be measured against it: " + (tooShort.isEmpty() ? juce::String ("all do")
                                                                    : tooShort.joinIntoString ("; ")));

        check (leaks.isEmpty(), "not one file in the library puts meta or sysex on the wire: "
               + (leaks.isEmpty() ? juce::String ("none did") : leaks.joinIntoString ("; ")));

        check (wrongCount.isEmpty(), "one pass of every file emits exactly its own key-downs and its "
               "own key-ups, no more and none missing: "
               + (wrongCount.isEmpty() ? juce::String ("none lost") : wrongCount.joinIntoString ("; ")));

        check (altered.isEmpty(), "the pitches and velocities that come out are the ones that are in "
               "the file: " + (altered.isEmpty() ? juce::String ("all agree") : altered.joinIntoString ("; ")));

        info ("no beat grid to follow: "
              + (smpteNamed.isEmpty() ? juce::String ("none in this library")
                                      : smpteNamed.joinIntoString ("; ")));

        check (! smpteNamed.isEmpty(), "the library's SMPTE-timed files are named here rather than "
               "quietly played as though they had a beat grid");

        {
            // A SMPTE file has seconds, not beats: with the switch on and off there is nothing to
            // disagree about, and saying so is the point.
            const juce::File smpte (juce::File (SKEER_FIXTURE_DIR)
                                        .getChildFile ("Misc").getChildFile ("SMPTE Melody.mid"));

            vault::MidiSource source;
            vault::MidiEmitter player;

            const bool read = source.load (smpte.getFullPathName());

            if (read)
                player.load (source.midiFile());

            if (read && player.loaded() && ! player.hasBeatGrid())
            {
                const auto span = (player.clipLengthSeconds() + 0.25) * 2.0;
                const auto on  = run (source.midiFile(), following, 0.0, span, 120.0);
                const auto off = run (source.midiFile(), absolute,  0.0, span, 120.0);

                check (on.events.size() == off.events.size()
                         && on.pitchSum() == off.pitchSum()
                         && on.keyDowns == off.keyDowns,
                       "for " + smpte.getFileName() + ", which is timed in frames, the switch changes "
                       "nothing -- there is no beat grid for it to abandon, and the clip runs in its "
                       "own seconds either way: " + juce::String (static_cast<int> (on.events.size()))
                       + " events and " + juce::String (on.keyDowns) + " key-downs on both settings");
            }
            else
            {
                check (false, smpte.getFileName() + " is the file that answers the SMPTE question, and "
                       "it has to be readable, playable and timed in frames to do it");
            }
        }

        info ("refused on the way in: " + refusedNames.joinIntoString ("; "));

        check (refused >= 3, "and " + juce::String (refused) + " file(s) the library ships as damage "
               "or as silence were refused: " + refusedNames.joinIntoString ("; "));
    }

    std::printf ("\n%d checks, %d failed\n", checks, failures);
    return failures > 0 ? 1 : 0;
}

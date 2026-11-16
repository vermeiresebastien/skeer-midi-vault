#include "VaultMidiEmitter.h"

#include <algorithm>
#include <cmath>

namespace vault
{
namespace
{
/** A key-up this class had to invent, because the transport ended under a note that was still
    down. Built rather than copied: the source never said to release it, the situation does. */
juce::MidiMessage releaseMessage (int channel, int pitch)
{
    return juce::MidiMessage::noteOff (channel, pitch, static_cast<juce::uint8> (0));
}

/** Quarter notes per minute from a tempo meta-event, or 0 when the bytes do not describe one.
    JUCE hands out seconds per quarter note and 0.0 for anything that is not a tempo event, so
    every caller has to treat 0 as "no tempo here" rather than as a tempo of none. */
double tempoBpmOf (const juce::MidiMessage& message)
{
    const auto secondsPerBeat = message.getTempoSecondsPerQuarterNote();

    return secondsPerBeat > 0 ? 60.0 / secondsPerBeat : 0.0;
}

int clampToBlock (int offset, int startSample, int numSamples)
{
    return juce::jlimit (startSample, startSample + numSamples - 1, offset);
}
} // namespace

//==============================================================================
void MidiEmitter::clear()
{
    events = {};
    tempoMap = {};
    sounding = {};

    beatsPerTick = secondsPerTick = clipBeats = clipSeconds = 0;
    initialTempo = 120;
    keyDownEvents = metaDiscarded = sysexDiscarded = 0;
    assumedTempo = false;

    reset();
}

void MidiEmitter::reset() noexcept
{
    hasAnchor = false;
    anchorBeat = lastBeat = 0;
}

void MidiEmitter::load (const juce::MidiFile& source)
{
    clear();

    const auto timeFormat = source.getTimeFormat();

    if (timeFormat > 0)
    {
        beatsPerTick = 1.0 / static_cast<double> (timeFormat);
    }
    else
    {
        // A negative division is SMPTE: the top byte holds the frame rate as a negative and the low
        // byte is ticks per frame. Misc/SMPTE Melody.mid is 0xe728, which as a short is -6360, and
        // -6360 >> 8 is -25 for 40 ticks per frame -- 1000 ticks per second. Masking the shifted
        // value with 0x7f turned -25 into 103, which is not a frame rate, and the file then looked
        // like it held nothing playable; an arithmetic right shift keeps the sign and needs no mask.
        const int frameRateCode = -(static_cast<int> (timeFormat) >> 8);
        const int ticksPerFrame = timeFormat & 0xff;

        // The same four rates midivault/engine/smf_parser.py accepts, and the same drop from 29 to
        // 29.97 that SMF means by it. Outside these the seconds this class computes and the seconds
        // the index recorded for the same bytes disagree, and a clip that is 3% off the grid the
        // browser says it is on is worse than one that says it cannot play.
        double framesPerSecond = 0;

        if (frameRateCode == 24 || frameRateCode == 25 || frameRateCode == 30)
            framesPerSecond = frameRateCode;
        else if (frameRateCode == 29)
            framesPerSecond = 29.97;

        if (! (framesPerSecond > 0) || ticksPerFrame <= 0)
            return;   // a header that does not describe a clock: there is nothing to play

        secondsPerTick = 1.0 / (framesPerSecond * ticksPerFrame);
    }

    struct Raw
    {
        double tick = 0;
        int track = 0, order = 0;
        juce::MidiMessage message;
    };

    std::vector<Raw> played;
    std::vector<Raw> tempoEvents;
    int order = 0;

    for (int t = 0; t < source.getNumTracks(); ++t)
    {
        const auto* track = source.getTrack (t);

        if (track == nullptr)
            continue;

        for (int i = 0; i < track->getNumEvents(); ++i)
        {
            const auto* holder = track->getEventPointer (i);

            if (holder == nullptr)
                continue;

            const auto& message = holder->message;
            const auto tick = juce::jmax (0.0, message.getTimeStamp());

            if (message.isMetaEvent())
            {
                ++metaDiscarded;

                if (message.isTempoMetaEvent())
                    tempoEvents.push_back ({ tick, t, order, message });

                continue;   // tempo, markers and text are read here, never handed to the host
            }

            if (message.isSysEx())
            {
                ++sysexDiscarded;
                continue;
            }

            ++order;
            played.push_back ({ tick, t, order, message });
        }
    }

    // Two tracks can state a tempo for the same tick. The lowest-numbered track wins and, inside
    // one track, the later event wins -- the rule midivault/engine/smf_parser.py applies to the
    // same bytes. If the two disagreed about where the seconds fall, the index and the plug-in
    // would be describing different performances of one piece of music.
    std::stable_sort (tempoEvents.begin(), tempoEvents.end(),
                      [] (const Raw& a, const Raw& b)
                      {
                          if (a.tick != b.tick)   return a.tick < b.tick;
                          if (a.track != b.track) return a.track > b.track;
                          return a.order < b.order;
                      });

    std::vector<Raw> unique;

    for (auto& candidate : tempoEvents)
    {
        auto bpm = tempoBpmOf (candidate.message);

        if (! (bpm > 0) || bpm > 1e6)
            continue;   // a tempo that cannot be played with: keep the running one

        if (! unique.empty() && unique.back().tick == candidate.tick)
            unique.back() = candidate;   // sorted so the winner of a tie arrives last
        else
            unique.push_back (candidate);
    }

    double lastTick = 0, lastSeconds = 0, currentBpm = 120;

    if (! unique.empty() && unique.front().tick == 0)
    {
        currentBpm = tempoBpmOf (unique.front().message);
        tempoMap.push_back ({ 0, 0, currentBpm });
        unique.erase (unique.begin());
    }
    else
    {
        // The map starts at bar one whether or not the file said how fast bar one is.
        tempoMap.push_back ({ 0, 0, currentBpm });
    }

    assumedTempo = unique.empty() && tempoEvents.empty();

    for (auto& candidate : unique)
    {
        const auto bpm  = tempoBpmOf (candidate.message);
        const auto tick = juce::jmax (lastTick, candidate.tick);

        if (tick == lastTick)
        {
            tempoMap.back().bpm = bpm;   // a later event at the same tick wins the tempo, not the row
            currentBpm = bpm;
            continue;
        }

        lastSeconds += (beatsPerTick > 0 ? (tick - lastTick) * beatsPerTick * 60.0 / currentBpm
                                         : (tick - lastTick) * secondsPerTick);
        lastTick   = tick;
        currentBpm = bpm;

        tempoMap.push_back ({ tick, lastSeconds, bpm });
    }

    initialTempo = tempoMap.front().bpm;

    std::stable_sort (played.begin(), played.end(),
                      [] (const Raw& a, const Raw& b)
                      {
                          if (a.tick != b.tick) return a.tick < b.tick;
                          return a.order < b.order;
                      });

    events.reserve (played.size());

    std::size_t cursor = 0;

    for (auto& raw : played)
    {
        Event event;
        event.beat    = beatsPerTick > 0 ? raw.tick * beatsPerTick : 0;
        event.seconds = secondsAt (raw.tick, cursor);
        event.message = raw.message;
        event.channel = raw.message.getChannel();

        if (raw.message.isNoteOn())
        {
            event.keyDown  = true;
            event.pitch    = raw.message.getNoteNumber();
            event.velocity = raw.message.getVelocity();
            ++keyDownEvents;
        }
        else if (raw.message.isNoteOff())
        {
            event.keyUp    = true;
            event.pitch    = raw.message.getNoteNumber();
            event.velocity = raw.message.getVelocity();
        }

        clipBeats   = juce::jmax (clipBeats, event.beat);
        clipSeconds = juce::jmax (clipSeconds, event.seconds);

        events.push_back (std::move (event));
    }
}

double MidiEmitter::secondsAt (double tick, std::size_t& cursor) const
{
    if (beatsPerTick <= 0)
        return tick * secondsPerTick;

    while (cursor + 1 < tempoMap.size() && tempoMap[cursor + 1].tick <= tick)
        ++cursor;

    const auto& point = tempoMap[cursor];
    return point.seconds + (tick - point.tick) * beatsPerTick * 60.0 / point.bpm;
}

//==============================================================================
MidiEmitter::Report MidiEmitter::process (const ClipTransport& transport, const Options& options,
                                          double sampleRate, int startSample, int numSamples,
                                          juce::MidiBuffer& output)
{
    Report report;

    if (events.empty() || numSamples <= 0 || sampleRate <= 0)
        return report;


    // Either the transport stopped or the host stopped saying where it is. Both mean the clip is
    // not running, and a note left down has to be released here: a plug-in that hangs a synth
    // because someone pressed stop is a defect the user can do nothing about.
    if (! transport.isPlaying || ! transport.hasPosition)
    {
        if (! sounding.empty())
        {
            report.flushed = true;

            for (auto& held : sounding)
            {
                output.addEvent (releaseMessage (held.channel, held.pitch),
                                 clampToBlock (startSample + report.keyUps, startSample, numSamples));
                ++report.keyUps;
            }

            sounding.clear();
        }

        reset();
        return report;
    }

    if (! hasAnchor || transport.beat < lastBeat - 1e-9)
    {
        // The first block of a run, or the host jumped backwards -- a seek, or its own loop coming
        // back to bar one. Either way the clip starts again at its own bar one from here, and it is
        // anchored to the reported position rather than accumulated from it: an accumulated clock
        // walks off the grid the moment the host moves.
        if (! sounding.empty())
        {
            report.flushed = true;

            for (auto& held : sounding)
            {
                output.addEvent (releaseMessage (held.channel, held.pitch),
                                 clampToBlock (startSample + report.keyUps, startSample, numSamples));
                ++report.keyUps;
            }

            sounding.clear();
        }

        anchorBeat = transport.beat;
        hasAnchor  = true;
    }

    lastBeat = transport.beat;

    const auto tempo     = transport.tempoBpm > 0 ? transport.tempoBpm : 120.0;
    const auto beatsUsed = transport.beat - anchorBeat;

    // Following the host, one file beat is one host beat and the clip lands on the grid at any
    // tempo. Not following -- or a file with SMPTE timing, which has no beat grid to follow -- the
    // clip runs in seconds of its own, so the coordinate space becomes seconds and the host tempo
    // only decides how many seconds have gone by since the anchor. The tempo is therefore read per
    // block: at a steady host tempo this is exact, and a host that ramps its tempo while following
    // is off cannot keep the clip on a grid that is itself moving.
    const auto bySeconds = ! options.followHostTempo || ! hasBeatGrid();
    const auto perSample = bySeconds ? (1.0 / sampleRate) : (tempo / 60.0 / sampleRate);
    const auto origin    = bySeconds ? (beatsUsed * 60.0 / tempo) : beatsUsed;
    const auto length    = bySeconds ? clipSeconds : clipBeats;

    if (! (length > 0) || ! (perSample > 0))
        return report;

    const auto windowEnd = origin + static_cast<double> (numSamples) * perSample;

    // A wrapped occurrence is not in the stream's order any more: the events that open the next
    // cycle come from the start of the file, so they can land at this cycle's end. Everything in
    // this block is therefore collected first and put back in clip time before it is quantised --
    // an event emitted at a sample earlier than one already in the buffer arrives out of order in
    // the host's own list, which is how a release can overtake the note it belongs to.
    struct Pending
    {
        double occurrence = 0;
        double pass = 0;
        const Event* event = nullptr;
    };

    std::vector<Pending> pending;

    for (auto& event : events)
    {
        const auto position = bySeconds ? event.seconds : event.beat;

        if (position >= windowEnd)
            break;   // the stream is in ascending time, so nothing later can be in this block

        auto occurrence = position;
        auto pass = 0.0;

        if (options.loop && occurrence < origin)
        {
            auto cycles = std::ceil ((origin - occurrence) / length - 1e-9);

            if (cycles < 0)
                cycles = 0;

            occurrence += cycles * length;

            if (occurrence < origin)
            {
                occurrence += length;   // the epsilon above can leave it a hair short
                ++cycles;
            }

            pass = cycles;

            if (occurrence < windowEnd)
                report.wrapped = true;
        }

        if (occurrence < origin || occurrence >= windowEnd)
            continue;

        pending.push_back ({ occurrence, pass, &event });
    }

    // The pass number breaks the tie the loop seam always produces: a clip that releases its last
    // note at exactly its own length meets its first note there, and the release of the cycle just
    // ended has to reach the host before the key-down of the one starting -- same pitch, otherwise
    // the new note is switched off the instant it is struck. Within one pass the file's own order
    // is the author's, so it stands: a key-down and its release written in the same tick are a
    // zero-length note, not a note that never ends.
    std::stable_sort (pending.begin(), pending.end(),
                      [] (const Pending& a, const Pending& b)
                      {
                          if (a.occurrence != b.occurrence)  return a.occurrence < b.occurrence;
                          return a.pass < b.pass;
                      });

    for (const auto& candidate : pending)
    {
        auto& event = *candidate.event;

        // Events that quantise to the same sample are left in the same sample, in this order:
        // MidiBuffer inserts a new event after every event already at that time (its helper skips
        // entries whose time is <= the new one), so insertion order survives. VaultEmitTest measures
        // that rather than trusting it, because the whole ordering argument rests on it.
        const auto offset = clampToBlock (startSample
                                             + static_cast<int> ((candidate.occurrence - origin)
                                                                 / perSample),
                                         startSample, numSamples);

        auto message = event.message;

        if (event.keyDown || event.keyUp)
        {
            const auto transposed = event.pitch + options.transpose;

            // Checked before setting, not after: MidiMessage::setNoteNumber() clamps to the
            // keyboard range on its own, and a third that quietly became a unison is a wrong note
            // delivered as though it were right.
            if (transposed < 0 || transposed > 127)
            {
                ++report.droppedOutOfRange;
                continue;
            }

            if (transposed != event.pitch)
                message.setNoteNumber (transposed);
        }

        output.addEvent (message, offset);

        if (event.keyDown)
        {
            ++report.keyDowns;
            sounding.push_back ({ message.getChannel(), message.getNoteNumber(), event.velocity });
        }
        else if (event.keyUp)
        {
            ++report.keyUps;

            for (std::size_t i = sounding.size(); i > 0; --i)
            {
                if (sounding[i - 1].channel == message.getChannel()
                     && sounding[i - 1].pitch == message.getNoteNumber())
                {
                    sounding.erase (sounding.begin()
                                        + static_cast<std::ptrdiff_t> (i - 1));
                    break;
                }
            }
        }
        else if (message.isController())
            ++report.controllers;
        else if (message.isProgramChange())
            ++report.programs;
    }

    return report;
}

} // namespace vault

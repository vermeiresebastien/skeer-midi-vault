// Reading a source .mid the way the library means it: hashed with the app's convention, parsed
// without losing events, and refused or flagged when what is on disk is not what was indexed.
//
// Four claims. Three are about this reader alone; the fourth needs the index reader as well.
//
//   1. The digest this plug-in computes is the digest midivault/hashing.py stores. Pinned to
//      values produced twice over by tools that are neither Python nor this code -- sha256sum
//      and hashlib, which agreed -- so a green run is three-way agreement about what
//      files.content_hash means, not two implementations repeating one assumption.
//   2. juce::MidiFile gives up every event the file holds -- notes on all sixteen channels,
//      controllers, pitch wheel, program changes, sysex, tempo and time-signature meta. A parse
//      that dropped running status or a whole track would move a number here. Taking the same
//      tally after writing the file back out shows what the writer does to it: nothing shrinks,
//      and the only additions are the note-offs that close notes the source left open -- added
//      again on every pass, which is the measured reason MidiSource offers no re-encode.
//   3. Damage is recognised against the digest, not against whether the parser happens to cope.
//      In this run a one-byte edit still loads and a three-quarter copy does not, which is exactly
//      why the load is not the test: some damage plays as though the file were whole.
//   4. Index and bytes agree on the user's own library -- for rows read out of a live index, the
//      digest in content_hash is the digest of the file at that path. The browser stands on that
//      seam, and only a real scanner over real folders can be asked to testify to it.

#include <juce_audio_basics/juce_audio_basics.h>
#include <juce_core/juce_core.h>
#include <juce_cryptography/juce_cryptography.h>

#include <cstdio>
#include <vector>

#include "VaultIndexLocator.h"
#include "VaultIndexReader.h"
#include "VaultMidiSource.h"

#ifndef SKEER_FIXTURE_DIR
 #error "SKEER_FIXTURE_DIR must point at the repo's fixtures/demo_library"
#endif

namespace
{

int checks = 0;
int failures = 0;
int skipped = 0;

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

void skip (const juce::String& why)
{
    ++skipped;
    std::printf ("skip  %s\n", why.toRawUTF8());
}

bool readAllBytes (const juce::File& file, juce::MemoryBlock& out)
{
    juce::FileInputStream in (file);

    if (! in.openedOk())
        return false;

    const auto length = in.getTotalLength();

    if (length <= 0)
        return false;

    out.setSize (static_cast<int> (length));
    return in.read (out.getData(), static_cast<int> (length)) == static_cast<int> (length);
}

/** Everything the parser hands back, reduced to the numbers a listener would notice. Counting
    by message kind rather than comparing bytes is what makes a round trip meaningful: a
    re-encode is allowed to re-encode, it is not allowed to forget. */
struct Tally
{
    int events = 0, noteOns = 0, noteOffs = 0, controllers = 0, wheels = 0;
    int programs = 0, sysex = 0, meta = 0, tempos = 0, timeSignatures = 0, channels = 0;
    long long pitchSum = 0, velocitySum = 0;
    double lastTime = 0;

    bool operator== (const Tally& other) const
    {
        return events == other.events && noteOns == other.noteOns && noteOffs == other.noteOffs
            && controllers == other.controllers && wheels == other.wheels && programs == other.programs
            && sysex == other.sysex && meta == other.meta && tempos == other.tempos
            && timeSignatures == other.timeSignatures && channels == other.channels
            && pitchSum == other.pitchSum && velocitySum == other.velocitySum
            && lastTime == other.lastTime;
    }

    juce::String describe() const
    {
        return "events=" + juce::String (events) + " on=" + juce::String (noteOns)
             + " off=" + juce::String (noteOffs) + " cc=" + juce::String (controllers)
             + " wheel=" + juce::String (wheels) + " prog=" + juce::String (programs)
             + " sysex=" + juce::String (sysex) + " meta=" + juce::String (meta)
             + " tempo=" + juce::String (tempos) + " timesig=" + juce::String (timeSignatures)
             + " pitches=" + juce::String (pitchSum) + " velocities=" + juce::String (velocitySum)
             + " last=" + juce::String (lastTime);
    }
};

Tally tallyOf (const juce::MidiFile& file)
{
    Tally tally;

    for (int track = 0; track < file.getNumTracks(); ++track)
    {
        const auto* sequence = file.getTrack (track);

        if (sequence == nullptr)
            continue;

        for (int i = 0; i < sequence->getNumEvents(); ++i)
        {
            const auto* holder = sequence->getEventPointer (i);

            if (holder == nullptr)
                continue;

            const auto& message = holder->message;

            ++tally.events;

            if (message.isNoteOn())              { ++tally.noteOns;  tally.pitchSum += message.getNoteNumber();
                                                   tally.velocitySum += message.getVelocity(); }
            else if (message.isNoteOff())        { ++tally.noteOffs; tally.pitchSum += message.getNoteNumber(); }
            else if (message.isController())     { ++tally.controllers; }
            else if (message.isPitchWheel())     { ++tally.wheels; }
            else if (message.isProgramChange())  { ++tally.programs; }
            else if (message.isSysEx())          { ++tally.sysex; }

            if (message.isMetaEvent())
            {
                ++tally.meta;

                if (message.getMetaEventType() == 0x51) ++tally.tempos;
                if (message.getMetaEventType() == 0x58) ++tally.timeSignatures;
            }

            // Only note messages have a channel worth counting. getChannel() on meta is not a
            // channel at all, and folding it in would make "all sixteen channels" true by accident.
            if (message.isNoteOnOrOff())
                tally.channels |= (1 << (message.getChannel() - 1));

            tally.lastTime = juce::jmax (tally.lastTime, message.getTimeStamp());
        }
    }

    return tally;
}

/** A file designed to be awkward: sixteen channels, velocity-0 note-ons, long controller
    streams, two tempos, a time signature, sysex and text meta spread over three tracks. */
juce::MidiFile makeAwkwardFile()
{
    juce::MidiFile file;
    file.setTicksPerQuarterNote (96);

    juce::MidiMessageSequence conductor;
    conductor.addEvent (juce::MidiMessage::tempoMetaEvent (500000), 0.0);          // 120 bpm
    conductor.addEvent (juce::MidiMessage::timeSignatureMetaEvent (4, 4), 0.0);
    conductor.addEvent (juce::MidiMessage::tempoMetaEvent (615384), 384.0);        // 97.5 bpm
    conductor.addEvent (juce::MidiMessage::textMetaEvent (0x01, "Fender Rhodes"), 768.0);
    file.addTrack (conductor);

    juce::MidiMessageSequence keys;

    for (int channel = 1; channel <= 16; ++channel)
    {
        const auto tick = static_cast<double> (channel * 7);

        keys.addEvent (juce::MidiMessage::programChange (channel, channel * 3), tick);
        keys.addEvent (juce::MidiMessage::noteOn (channel, 48 + channel,
                                                 static_cast<unsigned char> (channel * 8)), tick);

        // A velocity-0 note-on is a note-off wearing a note-on's opcode. JUCE reads it that way
        // by default -- isNoteOn(false) rejects it, isNoteOff(true) claims it -- so it belongs in
        // the key-up count here rather than vanishing or registering as a silent key press.
        keys.addEvent (juce::MidiMessage::noteOn (channel, 60, static_cast<unsigned char> (0)),
                       tick + 24.0);

        keys.addEvent (juce::MidiMessage::noteOff (channel, 48 + channel,
                                                  static_cast<unsigned char> (channel * 8)), tick + 48.0);
    }

    file.addTrack (keys);

    juce::MidiMessageSequence controls;

    for (int i = 0; i < 40; ++i)
        controls.addEvent (juce::MidiMessage::controllerEvent (10, i % 120,
                                                               static_cast<unsigned char> (i * 3)),
                           static_cast<double> (i * 11));

    for (int i = 0; i < 12; ++i)
        controls.addEvent (juce::MidiMessage::pitchWheel (10, i * 500), static_cast<double> (i * 37));

    const unsigned char sysexBytes[] = { 0xf0, 0x7e, 0x7f, 0x06, 0x01, 0xf7 };
    controls.addEvent (juce::MidiMessage (sysexBytes, static_cast<int> (sizeof (sysexBytes))), 0.0);
    file.addTrack (controls);

    return file;
}

bool writeMidiFile (const juce::File& file, const juce::MidiFile& midi)
{
    juce::FileOutputStream out (file);

    if (! out.openedOk())
        return false;

    return midi.writeTo (out, 1);
}

juce::MemoryBlock encode (const juce::MidiFile& midi)
{
    juce::MemoryOutputStream out;

    return midi.writeTo (out, 1) ? juce::MemoryBlock (out.getData(), out.getDataSize())
                                 : juce::MemoryBlock();
}

juce::MidiFile decode (const juce::MemoryBlock& bytes, bool& ok)
{
    juce::MemoryInputStream in (bytes, false);

    juce::MidiFile midi;
    ok = midi.readFrom (in);
    return midi;
}

} // namespace

int main()
{
    std::printf ("SKEER MIDI VAULT source-file test\n================================\n\n");

    const auto sandbox = juce::File::getSpecialLocation (juce::File::currentExecutableFile)
                             .getParentDirectory().getChildFile ("midivault-midi-sandbox");

    sandbox.deleteRecursively();

    if (! sandbox.createDirectory())
    {
        std::printf ("FAIL  the sandbox beside the exe could not be created: %s\n",
                     sandbox.getFullPathName().toRawUTF8());
        return 1;
    }

    const auto awkward = sandbox.getChildFile ("awkward.mid");
    const auto original = makeAwkwardFile();

    if (! writeMidiFile (awkward, original))
    {
        std::printf ("FAIL  the awkward fixture could not be written to %s\n",
                     awkward.getFullPathName().toRawUTF8());
        return 1;
    }

    //=========================================================================
    // 1. Reading what the library points at
    //=========================================================================
    vault::MidiSource source;
    juce::String failureReason;

    if (! source.load (awkward.getFullPathName()))
        failureReason = source.errorMessage();

    check (source.loaded(), "the awkward fixture loads: " + failureReason);

    const auto parsed = tallyOf (source.midiFile());

    std::printf ("info  parsed tally: %s\n", parsed.describe().toRawUTF8());

    check (source.timeFormat() == 96, "the ticks-per-quarter-note the file declares is the one on hand");
    check (source.numTracks() == 3, "and all three tracks are there, not just the first");
    check (parsed.noteOns == 16 && parsed.noteOffs == 32,
           "sixteen key-downs and thirty-two key-ups arrive, the velocity-0 ones counted as up");
    check (parsed.controllers == 40 && parsed.wheels == 12,
           "the controller and pitch-wheel streams are whole: a dropped running status counts short");
    check (parsed.programs == 16, "every program change is still a program change");
    check (parsed.tempos == 2 && parsed.timeSignatures == 1,
           "and the tempo map and time signature are readable, which is what a beat grid needs");
    check (parsed.sysex == 1, "the system-exclusive message survived, as it must for a file that carries one");
    check (parsed.meta >= 4, "text meta is kept rather than skipped as noise");

    int channelsTouched = 0;

    for (int bit = 0; bit < 16; ++bit)
        if ((parsed.channels & (1 << bit)) != 0)
            ++channelsTouched;

    std::printf ("info  channels touched: %d\n", channelsTouched);
    check (parsed.channels == 0xffff, "all sixteen MIDI channels are represented");

    const auto recordedHash = source.contentHash();

    std::printf ("info  content hash: %s (%lld bytes)\n", recordedHash.toRawUTF8(),
                 static_cast<long long> (source.bytes()));

    check (recordedHash.length() == 64,
           "the digest is 64 hex characters, the shape of what files.content_hash holds");

    //=========================================================================
    // 2. The digest convention, pinned by tools that are neither Python nor this code
    //=========================================================================
    {
        struct Pinned { const char* relative; const char* digest; };

        const Pinned pinned[] = {
            { "Drums/Trap Hat Pattern 140.mid",
              "e2ed4446abfff1ff9ce87d877ff0f95196b6b6792b32c821d2a618601e077d81" },
            { "Bass/Funk Bassline F.mid",
              "037a56a317fd875228c0c0753ef34886f872f96d71edcb2c92da230976307362" },
            { "Full Arrangements/Odd Meter 7-8.mid",
              "7f31e2b29370590ab41a27350642e8f05d4ab550ccd7db7bda5e08125510700a" },
        };

        const juce::File library (SKEER_FIXTURE_DIR);

        for (const auto& entry : pinned)
        {
            const auto file = library.getChildFile (entry.relative);

            vault::MidiSource one;

            if (! one.load (file.getFullPathName()))
            {
                check (false, juce::String (entry.relative) + " loads to check its digest: "
                              + one.errorMessage());
                continue;
            }

            check (one.contentHash() == entry.digest,
                   "the digest of " + juce::String (entry.relative)
                   + " is what sha256sum and hashlib both printed");

            // A browser hands the plug-in files.content_hash for the row it listed, and this call is
            // the only thing that decides whether the bytes match it. Exercised here on the same
            // file, so the seam between the two halves of step 4 is covered by a real value rather
            // than by one made up for a mock.
            check (one.checkAgainst (entry.digest) == vault::HashCheck::matches,
                   "and " + juce::String (entry.relative) + " hashes to the digest its row holds");
        }
    }

    //=========================================================================
    // 3. What the writer does to a file that has nothing wrong with it
    //
    // The plug-in never hands a host a re-encode, and section 6 measures why. This section keeps
    // that finding honest from the other side: on a file whose notes are all closed, the round
    // trip is a fixed point. So the growth measured later is the price of closing open notes, not
    // of writing at all. encode() and decode() are the test's window on JUCE's writer.
    //=========================================================================
    {
        const auto roundTrip = encode (source.midiFile());

        check (roundTrip.getSize() > 0, "the parsed file encodes back to bytes");

        const auto reWritten = sandbox.getChildFile ("awkward-roundtrip.mid");
        reWritten.replaceWithData (roundTrip.getData(), roundTrip.getSize());

        vault::MidiSource again;

        if (! again.load (reWritten.getFullPathName()))
        {
            check (false, "and the re-written file reads back: " + again.errorMessage());
        }
        else
        {
            const auto second = tallyOf (again.midiFile());

            std::printf ("info  round-trip tally: %s\n", second.describe().toRawUTF8());

            check (second == parsed,
                   "one pass through the writer and reader changes nothing a listener could hear");
            check (again.timeFormat() == source.timeFormat(),
                   "and the beat grid's unit is identical after the round trip");

            // Whether the re-encoded bytes equal the file on disk is a fact about JUCE's writer,
            // not a promise this plug-in makes, so it is reported. What IS asserted is that a
            // second pass is the same bytes as the first: no need to close anything, no drift.
            std::printf ("info  re-encoded bytes identical to the original: %s\n",
                         again.contentHash() == recordedHash ? "yes" : "no");

            check (encode (again.midiFile()) == roundTrip,
                   "and writing it a second time produces the same bytes, so a file with its notes "
                   "already closed is a fixed point");
        }
    }

    //=========================================================================
    // 4. What the hash catches that the parser cannot
    //=========================================================================
    {
        juce::MemoryBlock tampered;

        if (! readAllBytes (awkward, tampered) || tampered.getSize() == 0)
        {
            check (false, "the fixture could be read back for tampering");
        }
        else
        {
            // Same bytes, one of them different. The parser still succeeds -- which is the point:
            // only the digest tells the plug-in it is not looking at the indexed file.
            auto* data = static_cast<unsigned char*> (tampered.getData());
            data[tampered.getSize() / 2] = static_cast<unsigned char> (data[tampered.getSize() / 2] ^ 0x11);

            const auto edited = sandbox.getChildFile ("awkward-tampered.mid");
            edited.replaceWithData (tampered.getData(), tampered.getSize());

            vault::MidiSource suspect;
            const bool suspectLoaded = suspect.load (edited.getFullPathName());

            std::printf ("info  tampered file: loaded=%s hash %s the recorded one\n",
                         suspectLoaded ? "yes" : "no",
                         suspect.checkAgainst (recordedHash) == vault::HashCheck::differs
                             ? "differs from" : "does not match");

            check (suspect.checkAgainst (recordedHash) != vault::HashCheck::notRecorded
                     && suspect.checkAgainst (recordedHash) != vault::HashCheck::matches,
                   "a file with one byte changed is never called the file the index describes");
            check (suspect.contentHash() != recordedHash,
                   "and the flag comes from the digest, not from the name or the timestamp");
        }

        // A copy that stopped early. Truncation is what a listener hears as "the loop got
        // shorter", so it has to be recognisable before playback rather than after.
        juce::MemoryBlock shortCopy;

        if (readAllBytes (awkward, shortCopy))
        {
            shortCopy.setSize (static_cast<int> (shortCopy.getSize() * 3 / 4));

            const auto truncated = sandbox.getChildFile ("awkward-truncated.mid");
            truncated.replaceWithData (shortCopy.getData(), shortCopy.getSize());

            vault::MidiSource cut;
            const bool cutLoaded = cut.load (truncated.getFullPathName());

            std::printf ("info  truncated file: loaded=%s %s\n", cutLoaded ? "yes" : "no",
                         cutLoaded ? tallyOf (cut.midiFile()).describe().toRawUTF8()
                                   : cut.errorMessage().toRawUTF8());

            check (cut.checkAgainst (recordedHash) != vault::HashCheck::matches,
                   "a file that stops short is never mistaken for the one the library indexed");
        }

        check (vault::MidiSource().checkAgainst ("") == vault::HashCheck::notRecorded,
               "and a row the scanner never hashed is called unknown, not silently called a match");
    }

    //=========================================================================
    // 5. Things that are not MIDI files
    //=========================================================================
    {
        const auto notAMidi = sandbox.getChildFile ("shopping-list.txt");
        notAMidi.replaceWithData ("milk, eggs, one standard midi file (not)", 45);

        vault::MidiSource junk;
        const bool junkLoaded = junk.load (notAMidi.getFullPathName());

        check (! junkLoaded && junk.errorMessage().isNotEmpty(),
               "a text file named .mid is refused with a reason, not played as silence: "
               + junk.errorMessage());

        vault::MidiSource missing;
        const bool missingLoaded = missing.load (sandbox.getChildFile ("nowhere.mid").getFullPathName());

        check (! missingLoaded && missing.errorMessage().isNotEmpty(),
               "and a path with no file at all says so: " + missing.errorMessage());
    }

    //=========================================================================
    // 6. The shipped demo library, every file in it
    //
    // Misc/ is not a pile of songs: it is the app's own adversarial set -- a corrupt chunk, a
    // truncated file, a text file with a .mid name, a format-2 sequence, SMPTE timing, meta-only.
    // So "all of them parse" is the wrong claim. The right one is that the files the library
    // means as garbage are refused out loud, every other file gives up its whole content, and on
    // the way back out nothing ever disappears -- the only thing that can be added is the note-off
    // that closes a note the source left open, and that addition does not stop after one pass.
    //=========================================================================
    {
        const juce::File library (SKEER_FIXTURE_DIR);
        const auto files = library.findChildFiles (juce::File::findFiles, true, "*.mid");

        info ("demo library: " + library.getFullPathName());

        check (files.size() >= 30, "the tracked demo library is where the repo says it is and holds "
               + juce::String (files.size()) + " MIDI files");

        int loaded = 0, hashed = 0, refused = 0, growing = 0;
        juce::StringArray refusedNames, loadFailures, keyDownsLost, extraEvents;
        juce::StringArray shrank, neverStopped, growthNamed;

        for (const auto& file : files)
        {
            const auto name = file.getFileName();
            const bool meantAsGarbage = name.containsIgnoreCase ("Corrupt")
                                     || name.containsIgnoreCase ("Truncated")
                                     || name.containsIgnoreCase ("Not A Midi");

            vault::MidiSource one;

            if (! one.load (file.getFullPathName()))
            {
                ++refused;
                refusedNames.add (name);

                if (! meantAsGarbage)
                    loadFailures.add (name + ": " + one.errorMessage());

                std::printf ("      %-32s refused  %s\n", name.toRawUTF8(),
                             one.errorMessage().toRawUTF8());
                continue;
            }

            ++loaded;

            if (one.contentHash().length() == 64)
                ++hashed;

            if (meantAsGarbage)
                loadFailures.add (name + ": accepted, but the library ships it as garbage");

            const auto before = tallyOf (one.midiFile());

            // encode() and decode() here are the test's own window on JUCE's writer, not the
            // plug-in's API: MidiSource deliberately offers no way to re-encode, because the
            // measurements below are the reason.
            bool decoded = false;
            auto current = decode (encode (one.midiFile()), decoded);

            const auto after = decoded ? tallyOf (current) : Tally();

            if (! decoded || current.getNumTracks() != one.numTracks()
                           || after.noteOns != before.noteOns)
            {
                keyDownsLost.add (name + " (" + before.describe() + " -> " + after.describe() + ")");
            }
            else if (after.events - before.events != after.noteOffs - before.noteOffs)
            {
                // Re-encoding is allowed to add the note-off that closes a note the source left
                // open -- juce::MidiFile::readNextTrack calls updateMatchedPairs() for exactly
                // that reason, and an un-closed note is a stuck key in whatever plays it next.
                // Nothing else may appear, and nothing may disappear.
                extraEvents.add (name + " (" + before.describe() + " -> " + after.describe() + ")");
            }

            // The question a drag-and-drop export has to answer: does the growth stop? Two further
            // passes answer it. Measured on this JUCE, a file with overlapping notes adds the same
            // number of note-offs every single pass -- Funk Bassline F goes 149, 170, 191, 212 --
            // so it does not converge, it inflates. Freezing those numbers as a requirement would
            // be over-fitting to thirty fixtures; what is required instead is the two properties
            // the design decision actually rests on: a pass never removes anything, and a file that
            // gained closing note-offs has not stopped gaining them by the third pass.
            std::vector<Tally> passes;
            passes.push_back (before);
            passes.push_back (after);

            bool chainOk = decoded;

            for (int pass = 0; pass < 2 && chainOk; ++pass)
            {
                bool ok = false;
                current = decode (encode (current), ok);

                if (! ok)
                {
                    chainOk = false;
                    break;
                }

                passes.push_back (tallyOf (current));
            }

            if (! chainOk || passes.size () != 4)
            {
                keyDownsLost.add (name + " (could not be written and read back three times)");
                continue;
            }

            juce::String steps;

            for (int i = 0; i < 4; ++i)
                steps += (i > 0 ? " -> " : "") + juce::String (passes[i].noteOffs);

            bool onlyGrows = true;

            for (int i = 1; i < 4; ++i)
            {
                if (passes[i].noteOffs < passes[i - 1].noteOffs
                 || passes[i].noteOns  != passes[i - 1].noteOns
                 || passes[i].events   - passes[i - 1].events
                    != passes[i].noteOffs - passes[i - 1].noteOffs)
                {
                    onlyGrows = false;
                }
            }

            if (! onlyGrows)
            {
                // Something disappeared, or an event that is not a closing note-off appeared. Both
                // would mean a re-encode is unsafe to hand anyone at all.
                shrank.add (name + " (key-ups " + steps + ", events "
                            + juce::String (passes[0].events) + " -> "
                            + juce::String (passes[3].events) + ")");
            }
            else if (passes[1].noteOffs != before.noteOffs && passes[3].noteOffs <= passes[2].noteOffs)
            {
                neverStopped.add (name + " (key-ups " + steps + " -- grew, then settled)");
            }
            else if (passes[1].noteOffs != before.noteOffs)
            {
                ++growing;
                growthNamed.add (name + " (" + steps + ")");
            }

            std::printf ("      %-32s %d tracks, %d events, %d bytes, key-ups %s\n", name.toRawUTF8(),
                         one.numTracks(), before.events, static_cast<int> (one.bytes()),
                         steps.toRawUTF8());
        }

        std::printf ("info  loaded=%d hashed=%d refused=%d of %d, %d of them inflating every pass\n",
                     loaded, hashed, refused, files.size(), growing);

        if (growthNamed.size() > 0)
        {
            std::printf ("info  every key-up count is the source's, plus one fixed step per pass:\n");

            for (const auto& line : growthNamed)
                std::printf ("      %s\n", line.toRawUTF8());
        }

        check (loadFailures.isEmpty(), "only the files the library means as garbage are refused: "
               + loadFailures.joinIntoString ("; "));
        check (refused >= 3, "and the garbage really is refused -- it named "
               + refusedNames.joinIntoString (", "));
        check (hashed == loaded, "every file that loaded has a 64-character digest to store");
        check (keyDownsLost.isEmpty(),
               "no key-down is lost by re-encoding any file in the library: "
               + keyDownsLost.joinIntoString ("; "));
        check (extraEvents.isEmpty(),
               "and on the first pass nothing but a closing note-off can appear: "
               + extraEvents.joinIntoString ("; "));
        check (shrank.isEmpty(),
               "and across three passes a round trip never removes anything or adds any other kind "
               "of event: " + shrank.joinIntoString ("; "));
        check (neverStopped.isEmpty(),
               "a file that gained closing note-offs has not stopped gaining them by the third "
               "pass -- the growth has no fixed point, which is why the plug-in will copy source "
               "bytes for a drag rather than write out its own parse: "
               + neverStopped.joinIntoString ("; "));
    }

    //=========================================================================
    // 7. The two halves meeting over the user's own library
    //
    // Sections 2 and 6 are each about one side: a digest computed from bytes, a column read out of
    // an index. The claim the browser depends on is that they are the same number for the same
    // file -- that is what lets the plug-in say "this is the file you searched for" and play it.
    // Only an index built by the real scanner over real folders can answer that, so where there is
    // none, this section reports a skip rather than passing quietly.
    //=========================================================================
    {
        const auto indexPath = vault::resolveIndex (vault::IndexRoots::fromRuntime());

        if (indexPath.isEmpty())
        {
            skip ("no SKEER MIDI VAULT index is installed here, so the row-and-bytes cross-check "
                  "did not run");
        }
        else
        {
            vault::IndexReader index;

            // SQLite creates -shm beside a WAL index the moment it is opened, even read-only, so a
            // process that is not allowed to write that folder cannot open it at all. Without this
            // probe a sandboxed run would report a broken reader; the same probe guards the live
            // half of VaultIndexTest for the same reason.
            const juce::File indexFile (indexPath);
            const juce::File probe = indexFile.getParentDirectory()
                                         .getChildFile ("midivault-midi-probe.tmp");

            const bool writable = probe.replaceWithData ("x", 1);

            if (writable)
                probe.deleteFile();

            if (! writable)
            {
                skip ("the folder holding the live index will not let this process create the -shm "
                      "file SQLite needs to read it, so the cross-check did not run: "
                      + indexFile.getParentDirectory().getFullPathName());
            }
            else if (! index.open (indexPath))
            {
                check (false, "the live index opens for the cross-check: " + index.errorMessage());
            }
            else
            {
                info ("live index: " + indexPath);

                const auto rows = index.listFiles (10, {});

                int agreed = 0, disagreed = 0, unreadable = 0;
                juce::StringArray what;

                for (const auto& row : rows)
                {
                    vault::MidiSource file;

                    if (! file.load (row.path))
                    {
                        // A row can legitimately point at a file that moved since the last scan.
                        // That is not a disagreement about content, so it is counted and reported
                        // separately instead of being allowed to fail the claim.
                        ++unreadable;
                        what.add (row.filename + " (not read: " + file.errorMessage() + ")");
                        continue;
                    }

                    // Case-sensitive on purpose. content_hash is hashlib's hexdigest; an agreement
                    // that only holds because a comparison forgives a difference is not agreement.
                    const bool sameBytes = row.contentHash.isNotEmpty()
                                        && file.contentHash() == row.contentHash;

                    if (sameBytes && file.checkAgainst (row.contentHash) == vault::HashCheck::matches)
                    {
                        ++agreed;
                    }
                    else
                    {
                        ++disagreed;
                        what.add (row.filename + " (row " + row.contentHash.substring (0, 12)
                                  + " vs bytes " + file.contentHash().substring (0, 12) + ")");
                    }
                }

                std::printf ("info  cross-check over %d live rows: agreed=%d disagreed=%d "
                             "not-on-disk=%d\n", static_cast<int> (rows.size()),
                             agreed, disagreed, unreadable);

                for (const auto& line : what)
                    std::printf ("      %s\n", line.toRawUTF8());

                check (! rows.empty(), "the live index has rows for the cross-check to read");
                check (disagreed == 0 && agreed > 0,
                       "not one row of the real library disagrees with the bytes at its path, and "
                       + juce::String (agreed) + " of " + juce::String (static_cast<int> (rows.size()))
                       + " were checked: " + what.joinIntoString ("; "));

                index.close();
            }
        }
    }

    sandbox.deleteRecursively();

    std::printf ("\n%d checks, %d failed, %d skipped\n", checks, failures, skipped);
    return failures > 0 ? 1 : 0;
}

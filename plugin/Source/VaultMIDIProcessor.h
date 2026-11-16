#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

#include "VaultMidiEmitter.h"
#include "VaultMidiSource.h"

// The VST3 form of MIDI VAULT: a MIDI effect that browses the local index and plays the selected
// file against the host's transport. This class is the seam between the parameters a producer
// touches and the clip clock in vault::MidiEmitter; what the clip does -- beat grid, tempo switch,
// transpose, loop -- is decided there and tested there, and this file owns only the wiring: the
// AudioProcessorValueTreeState, the play head, the loaded file, and the state a host saves.
//
// The editor comes in step 6, which is why hasEditor() is still false.
class VaultMIDIProcessor : public juce::AudioProcessor
{
public:
    /** What the browser has to be able to say about the clip without reaching into the emitter
        while the audio thread is reading it. One lock, one copy, taken off the audio thread. */
    struct ClipStatus
    {
        bool loaded = false;
        bool hasBeatGrid = true;        // false: SMPTE timing, so nothing to follow
        bool tempoIsAssumed = false;    // true: the file never said, and 120 BPM is a guess
        bool waitingForTransport = false;
        int  notes = 0, discardedMeta = 0, discardedSysEx = 0;
        double lengthBeats = 0, lengthSeconds = 0, initialTempoBpm = 0;

        /** Of the bytes last read, in the app's own convention. The browser needs it because a
            path is not the library: it is the index row that says what these bytes were meant to
            be, and only these two values compared can tell the user they are not. */
        juce::String contentHash;
        juce::int64 bytesOnDisk = 0;

        /** Two paths, and a reader has to know which question it is asking. `file` is what is
            actually playing: the file the clip in memory was read from, empty when nothing is
            loaded. `savedFile` is what the state names -- the project's claim about which file it
            wants -- and it survives a failed restore, because a project whose audio lives on an
            unmounted drive still says where it wanted it. Branch the verdict sentence on `restore`
            (which distinguishes gone from unreadable), print `savedFile` when naming the file the
            project wanted, and use `file` only for "what you are hearing now". The two are equal
            after any successful load and differ exactly while a restore could not read its file. */
        juce::String file, savedFile;
        juce::String error;

        /** What the saved project said the bytes were, against what is on disk now. `nothingSaved`
            also covers a state blob written before the hash key existed: with nothing recorded
            there is nothing to claim either way. A `differs` clip still loads and plays -- the
            user stays authoritative about what should be heard -- and the verdict is here so the
            browser can say that the file under that name is not the one the project was built on.
            `missing` and `unreadable` both mean nothing is loaded from the project and `error` says
            why: the first that the path is not there, the second that something is there and will
            not open or parse as MIDI. They are separate because a deleted file and a file that was
            replaced by something else ask the user to do different things. */
        enum class RestoreCheck
        {
            nothingSaved,
            matches,
            differs,
            missing,
            unreadable,
        };

        RestoreCheck restore = RestoreCheck::nothingSaved;
        juce::String savedHash;      // the digest the state recorded; empty when none did
        int savedStateVersion = 0;   // 0 when the blob pre-dates the version key
    };

    VaultMIDIProcessor();
    ~VaultMIDIProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;

    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return false; }

    const juce::String getName() const override { return "SKEER MIDI VAULT"; }

    bool acceptsMidi() const override { return true; }
    bool producesMidi() const override { return true; }
    bool isMidiEffect() const override { return true; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    /** Points the plug-in at one library file and puts its clip on the clock. False leaves the
        plug-in silent, with errorMessage() saying why in terms a user can act on. */
    bool loadFile (const juce::String& filePath);

    void unload();

    ClipStatus status() const;
    juce::String errorMessage() const;

    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    /** The three controls the plug-in has, in the order the editor will lay them out. Public
        because the checks and, later, the GUI both address the parameters by these ids rather
        than by scanning the host's parameter list for a matching name. */
    static constexpr auto followTempoId = "followHostTempo";
    static constexpr auto transposeId   = "transpose";
    static constexpr auto loopId        = "loop";

    juce::AudioProcessorValueTreeState valueTreeState;

private:
    /** Key on the loaded file inside the saved state. It travels with the parameters because a
        host project has to come back with the same clip under the same transpose. */
    static const juce::Identifier sourceFileKey;

    /** The digest the loaded bytes had, and which keys this build writes. Saved beside the path so
        a returning project can tell a file that moved from a file whose bytes were replaced under
        the same name -- the difference `MidiSource::checkAgainst` exists to name. */
    static const juce::Identifier sourceHashKey;
    static const juce::Identifier stateVersionKey;
    static constexpr int currentStateVersion = 2;   // 1 was the path alone, with no version key

    /** The one load path. A file picked by hand records no hash and is not a restore; a project
        coming back passes what it saved. The file is opened, hashed and parsed with no lock held,
        and stateLock is taken only to publish the result. A failure leaves the clip already in
        memory alone -- a failed pick must not stop an audition -- and reports why through `error`
        and `lastFailure`; setStateInformation is what clears it, because a project that cannot
        restore its file has nothing to keep playing. */
    bool load (const juce::String& filePath, const juce::String& recordedHash, int recordedVersion);

    vault::MidiSource source;
    vault::MidiEmitter emitter;

    /** The path `source` was actually read from. The tree's sourceFile property is the path a
        *host project* saved, and the two may differ only while a restore is deciding what to do:
        status() reports this one as `file` and the property as `savedFile`, getStateInformation
        writes a digest only when this one and the property agree, and a restore that cannot load
        its file strips the tree's digest keys but keeps the path. No saved blob can therefore pair
        a path with a digest from a file it was not read from, and a project that could not find its
        file still remembers which one it wanted. Guarded by stateLock. */
    juce::String loadedPath;

    /** The verdict of the last restore, reported through status(). Guarded by stateLock. */
    ClipStatus::RestoreCheck restore = ClipStatus::RestoreCheck::nothingSaved;
    juce::String restoredHash;
    int restoredStateVersion = 0;

    /** Why the last load() failed, so a restore can tell a deleted file from one that is there and
        will not open without touching the filesystem a second time. Same lifecycle as `error`:
        written on a failed attempt, cleared by the next success and by unload(). Guarded by
        stateLock. */
    vault::MidiSource::LoadFailure lastFailure = vault::MidiSource::LoadFailure::none;

    // loadFile() opens, hashes and parses a file off disk on the GUI thread while processBlock() is
    // walking the clip it produced. Those three happen with no lock held; stateLock covers only the
    // publish -- the MidiSource move, emitter.load() (which flattens the clip once: O(events), a
    // few thousand small messages, reasoned rather than measured), the verdict fields and the three
    // ValueTree properties. So the audio thread waits for a vector swap and a flatten, not for file
    // I/O or SHA-256. The alternative is a lock-free double buffer that step 5 does not need yet.
    // Disclosed here because a race that has been traded for is a decision, not an oversight.
    mutable juce::CriticalSection stateLock;

    juce::String error;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (VaultMIDIProcessor)
};

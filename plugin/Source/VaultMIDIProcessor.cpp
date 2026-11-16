#include "VaultMIDIProcessor.h"

const juce::Identifier VaultMIDIProcessor::sourceFileKey { "sourceFile" };
const juce::Identifier VaultMIDIProcessor::sourceHashKey { "sourceHash" };
const juce::Identifier VaultMIDIProcessor::stateVersionKey { "stateVersion" };

// Follow Host Tempo is the useful default, but it is a switch and not a silent compensation:
// turning it off has to be something the user can see and pick, the same way every other automatic
// behaviour in this product is overridable. Loop is the same argument -- a clip that repeats
// forever in a host that was asked to play it once is the same kind of surprise -- and it defaults
// on because a four-bar phrase in an arrangement is expected to hold its ground, while the app's
// autoplay deck deliberately never wraps.
juce::AudioProcessorValueTreeState::ParameterLayout VaultMIDIProcessor::createParameterLayout()
{
    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    layout.add (std::make_unique<juce::AudioParameterChoice> (
        juce::ParameterID { followTempoId, 1 }, "Follow Host Tempo",
        juce::StringArray { "Off", "On" }, 1));

    layout.add (std::make_unique<juce::AudioParameterInt> (
        juce::ParameterID { transposeId, 1 }, "Transpose", -24, 24, 0));

    layout.add (std::make_unique<juce::AudioParameterChoice> (
        juce::ParameterID { loopId, 1 }, "Loop",
        juce::StringArray { "Once", "Loop" }, 1));

    return layout;
}

VaultMIDIProcessor::VaultMIDIProcessor()
    : AudioProcessor (BusesProperties()),
      valueTreeState (*this, nullptr, juce::Identifier ("VaultMIDI"), createParameterLayout())
{
}

VaultMIDIProcessor::~VaultMIDIProcessor() = default;

void VaultMIDIProcessor::prepareToPlay (double, int)
{
    // A restart of the engine is a new run of the transport as far as the clip is concerned: it
    // re-anchors at the first block that reports a position rather than resuming mid-phrase.
    const juce::ScopedLock sl (stateLock);
    emitter.reset();
}

void VaultMIDIProcessor::releaseResources()
{
}

void VaultMIDIProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    // BusesProperties() declares no audio buses, so this plugin moves MIDI and nothing else; the
    // buffer is cleared rather than passed through, because there is no signal in it to keep.
    buffer.clear();

    // A host with no audio bus still says how many frames this callback covers, but a zero-channel
    // AudioBuffer reports none, so the block size prepareToPlay was given is the fallback. Without
    // it the clip would have no window to fill and the plug-in would be silent in exactly the
    // hosts that need this line.
    const auto frames = buffer.getNumSamples() > 0 ? buffer.getNumSamples() : getBlockSize();
    const auto sampleRate = getSampleRate();

    if (frames <= 0 || sampleRate <= 0)
        return;

    vault::ClipTransport transport;

    if (auto* head = getPlayHead())
    {
        // Only legal here, on the audio thread. A host that reports no position at all gets a clip
        // that waits: guessing where bar one is would put the notes somewhere the grid is not.
        if (const auto position = head->getPosition())
        {
            if (const auto beat = position->getPpqPosition())
            {
                transport.beat        = *beat;
                transport.hasPosition = true;
            }

            if (const auto bpm = position->getBpm())
                transport.tempoBpm = *bpm;

            transport.isPlaying = position->getIsPlaying();
        }
    }

    vault::MidiEmitter::Options options;
    options.followHostTempo = valueTreeState.getRawParameterValue (followTempoId)->load() >= 0.5f;
    options.loop            = valueTreeState.getRawParameterValue (loopId)->load() >= 0.5f;
    options.transpose       = juce::roundToInt (valueTreeState.getRawParameterValue (transposeId)->load());

    const juce::ScopedLock sl (stateLock);
    emitter.process (transport, options, sampleRate, 0, frames, midi);
}

//==============================================================================
bool VaultMIDIProcessor::loadFile (const juce::String& filePath)
{
    // A pick, not a restore: nothing was recorded about these bytes, so nothing is claimed about
    // them. The path a project saved arrives through load() below instead.
    return load (filePath, {}, 0);
}

bool VaultMIDIProcessor::load (const juce::String& filePath, const juce::String& recordedHash,
                               int recordedVersion)
{
    // Nothing below this line is cheap: this is a file open, a SHA-256 of every byte and a full SMF
    // parse, all on the GUI thread while the audio thread is walking the clip that is already
    // playing. None of it runs under stateLock, because processBlock() blocks on that lock; the
    // publish at the end is the only part the audio thread can feel.
    vault::MidiSource candidate;

    if (! candidate.load (filePath))
    {
        const juce::ScopedLock sl (stateLock);

        error       = candidate.errorMessage();
        lastFailure = candidate.failure();

        // Nothing was read, so there is nothing to compare: status() must not keep a verdict from
        // whatever was loaded before this call. The clip itself is left alone -- a pick that goes
        // wrong must not stop the audition it interrupted. setStateInformation is what clears it,
        // because a project that cannot restore its file has nothing to keep playing.
        restore = ClipStatus::RestoreCheck::nothingSaved;
        restoredHash.clear();
        restoredStateVersion = 0;
        return false;
    }

    // Disclosed, never refused, and a string comparison rather than a second hash: both digests
    // already exist. A project whose file was edited under the same name still plays the bytes that
    // are there now -- the user is authoritative about what should be heard -- and the difference is
    // published through status() so the browser can say so.
    const auto check = candidate.checkAgainst (recordedHash);

    const juce::ScopedLock sl (stateLock);

    source  = std::move (candidate);
    emitter.load (source.midiFile());
    error.clear();
    lastFailure = vault::MidiSource::LoadFailure::none;

    // What is playing, as opposed to what a project saved. Only these two agreeing allows a digest
    // into a saved blob; see getStateInformation.
    loadedPath = filePath;

    restore = recordedHash.trim().isEmpty() ? ClipStatus::RestoreCheck::nothingSaved
                                            : (check == vault::HashCheck::matches
                                                   ? ClipStatus::RestoreCheck::matches
                                                   : ClipStatus::RestoreCheck::differs);
    restoredHash         = recordedHash;
    restoredStateVersion = recordedVersion;

    valueTreeState.state.setProperty (sourceFileKey, filePath, nullptr);
    valueTreeState.state.setProperty (sourceHashKey, source.contentHash(), nullptr);
    valueTreeState.state.setProperty (stateVersionKey, currentStateVersion, nullptr);
    return true;
}

void VaultMIDIProcessor::unload()
{
    const juce::ScopedLock sl (stateLock);

    emitter.clear();
    source.clear();
    loadedPath.clear();
    error.clear();
    lastFailure = vault::MidiSource::LoadFailure::none;
    restore = ClipStatus::RestoreCheck::nothingSaved;
    restoredHash.clear();
    restoredStateVersion = 0;
    valueTreeState.state.removeProperty (sourceFileKey, nullptr);
    valueTreeState.state.removeProperty (sourceHashKey, nullptr);
    valueTreeState.state.removeProperty (stateVersionKey, nullptr);
}

VaultMIDIProcessor::ClipStatus VaultMIDIProcessor::status() const
{
    const juce::ScopedLock sl (stateLock);

    ClipStatus clip;
    clip.loaded              = emitter.loaded();
    clip.hasBeatGrid         = emitter.hasBeatGrid();
    clip.tempoIsAssumed      = emitter.tempoIsAssumed();
    clip.waitingForTransport = emitter.waitingForTransport();
    clip.notes               = emitter.noteCount();
    clip.discardedMeta       = emitter.discardedMeta();
    clip.discardedSysEx      = emitter.discardedSysEx();
    clip.lengthBeats         = emitter.clipLengthBeats();
    clip.lengthSeconds       = emitter.clipLengthSeconds();
    clip.initialTempoBpm     = emitter.initialTempoBpm();
    clip.contentHash         = source.contentHash();
    clip.bytesOnDisk         = source.bytes();
    clip.file                = loadedPath;
    clip.savedFile           = valueTreeState.state.getProperty (sourceFileKey).toString();
    clip.error               = error;
    clip.restore             = restore;
    clip.savedHash           = restoredHash;
    clip.savedStateVersion   = restoredStateVersion;

    return clip;
}

juce::String VaultMIDIProcessor::errorMessage() const
{
    const juce::ScopedLock sl (stateLock);
    return error;
}

//==============================================================================
void VaultMIDIProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    // The parameters and the loaded path travel in the same tree: a saved project has to come back
    // with this clip under these settings, or the producer's arrangement lies.
    auto state = valueTreeState.copyState();

    // The digest and the schema version travel with the path, but only when the clip in memory is
    // the file this state names. load() already keeps both on the live tree; writing them here is
    // what makes the saved blob self-describing even for a state that was assembled by something
    // other than load(), and the version is how a future reader knows which keys to expect rather
    // than guessing at an older shape.
    //
    // The agreement check is the whole point. A failed restore puts the project's path in the tree
    // and leaves the previously loaded clip in memory, so `source.loaded()` alone would stamp that
    // clip's digest beside a path it was never read from -- and under this version key a reader
    // would take the pair as verified. A path with no digest is the honest shape of "this state
    // names a file and claims nothing about its bytes", which is also what loadFile() produces.
    {
        const juce::ScopedLock sl (stateLock);

        const auto treePath = valueTreeState.state.getProperty (sourceFileKey).toString();

        if (loadedPath.isNotEmpty() && loadedPath == treePath)
        {
            state.setProperty (stateVersionKey, currentStateVersion, nullptr);
            state.setProperty (sourceHashKey, source.contentHash(), nullptr);
        }
        else
        {
            state.removeProperty (sourceHashKey, nullptr);
            state.removeProperty (stateVersionKey, nullptr);
        }
    }

    std::unique_ptr<juce::XmlElement> xml (state.createXml());
    copyXmlToBinary (*xml, destData);
}

void VaultMIDIProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    std::unique_ptr<juce::XmlElement> xml (getXmlFromBinary (data, sizeInBytes));

    if (xml == nullptr || ! xml->hasTagName (valueTreeState.state.getType()))
        return;

    const auto path = xml->getStringAttribute (sourceFileKey.toString());

    // Read before the tree is replaced, because load() writes the current digest back over these
    // keys: the point of the comparison is what the project recorded, not what is there now. A
    // blob saved before this change carries neither attribute, which reads as "nothing recorded".
    const auto savedHash    = xml->getStringAttribute (sourceHashKey.toString());
    const auto savedVersion = xml->getIntAttribute (stateVersionKey.toString(), 0);

    valueTreeState.replaceState (juce::ValueTree::fromXml (*xml));

    // One case, not two: a blob that names no file and a blob whose file cannot be read both mean
    // "this project has no clip here". load() deliberately keeps the resident clip when a *pick*
    // fails, because a failed pick must not stop an audition; a restore is the opposite situation.
    // The project is claiming this file, and playing a different one under that claim is the lie
    // the hash key exists to prevent -- so the clip goes, and with it every field describing it.
    const auto restored = path.isNotEmpty() && load (path, savedHash, savedVersion);

    if (! restored)
    {
        const juce::ScopedLock sl (stateLock);

        // In the failure branch load() has already said why, in user terms. An empty path never
        // reached it, so say that instead rather than leaving a message from an earlier pick.
        if (path.isEmpty())
        {
            error       = "The project names no file to load";
            lastFailure = vault::MidiSource::LoadFailure::none;
        }

        emitter.clear();
        source.clear();
        loadedPath.clear();

        // "The file is gone" and "the file is there and will not open" ask the user to do different
        // things, and MidiSource is the only thing that knows which happened. A blob naming no file
        // is neither: nothing was ever named, so nothing is missing, and the state is the same one a
        // fresh instance reports.
        if (path.isEmpty())
            restore = ClipStatus::RestoreCheck::nothingSaved;
        else if (lastFailure == vault::MidiSource::LoadFailure::notFound)
            restore = ClipStatus::RestoreCheck::missing;
        else
            restore = ClipStatus::RestoreCheck::unreadable;

        restoredHash         = savedHash;
        restoredStateVersion = savedVersion;

        // What the clip was read from is gone, but what the project *wants* stays: the path is the
        // project's claim about intent, and a transient condition -- an unmounted drive, a folder
        // that is not reachable yet -- must not erase it from the user's arrangement. The digest
        // and the version do go, because those are claims about bytes nobody read; a path with no
        // digest is the honest shape of "this state names a file and claims nothing about its
        // bytes", and the gate in getStateInformation keeps it that way.
        valueTreeState.state.removeProperty (sourceHashKey, nullptr);
        valueTreeState.state.removeProperty (stateVersionKey, nullptr);
    }

    {
        const juce::ScopedLock sl (stateLock);
        emitter.reset();
    }
}

juce::AudioProcessorEditor* VaultMIDIProcessor::createEditor()
{
    return nullptr;
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new VaultMIDIProcessor();
}

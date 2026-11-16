#include "VaultMidiSource.h"

#include <juce_cryptography/juce_cryptography.h>

namespace vault
{

bool MidiSource::load (const juce::String& filePath)
{
    clear();

    const juce::File source (filePath);

    if (! source.existsAsFile())
    {
        error = "There is no file at " + filePath;
        loadFailure = LoadFailure::notFound;
        return false;
    }

    // One handle, two passes: SHA-256 consumes the stream, so it rewinds before parsing. The
    // hash is over every byte, exactly as sha256_file() does it in the service, which is what
    // makes the two values comparable at all.
    juce::FileInputStream input (source);

    if (! input.openedOk())
    {
        error = "The file is there but could not be opened: " + filePath;
        loadFailure = LoadFailure::unreadable;
        return false;
    }

    // files.content_hash holds hashlib's hexdigest, which is lowercase. JUCE's BigInteger already
    // prints lowercase -- measured, taking toLowerCase() out changes nothing today -- and the call
    // stays so the shape of the value this class publishes does not depend on a third party's
    // formatting choice. The comparison in checkAgainst is case-insensitive, so it would not
    // notice such a change on its own; VaultMidiTest's pinned digests and its live cross-check
    // are what would.
    hash = juce::SHA256 (input).toHexString().toLowerCase();
    numBytes = input.getTotalLength();
    input.setPosition (0);

    if (! file.readFrom (input))
    {
        error = filePath + " is not a Standard MIDI File that JUCE can read";
        file.clear();
        loadFailure = LoadFailure::unreadable;
        return false;
    }

    if (file.getNumTracks() == 0)
    {
        error = filePath + " has no tracks in it";
        file.clear();
        loadFailure = LoadFailure::unreadable;
        return false;
    }

    error.clear();
    loadFailure = LoadFailure::none;
    isLoaded = true;
    return true;
}

void MidiSource::clear()
{
    file.clear();
    hash.clear();
    error.clear();
    loadFailure = LoadFailure::none;
    numBytes = 0;
    isLoaded = false;
}

HashCheck MidiSource::checkAgainst (const juce::String& recordedHash) const
{
    if (recordedHash.trim().isEmpty())
        return HashCheck::notRecorded;

    return hash.equalsIgnoreCase (recordedHash.trim()) ? HashCheck::matches : HashCheck::differs;
}

} // namespace vault

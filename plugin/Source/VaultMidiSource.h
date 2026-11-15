#pragma once

#include <juce_audio_basics/juce_audio_basics.h>
#include <juce_core/juce_core.h>

namespace vault
{

/** What the index says about the bytes on disk versus what is actually on disk. */
enum class HashCheck
{
    matches,       // the file is the one the library described when it was scanned
    differs,       // someone edited, replaced or truncated it since
    notRecorded,   // the row carries no hash, so nothing can be claimed either way
};

/** One library file, read the way the library means it: the bytes are hashed with the app's own
    convention (SHA-256 of the whole content -- midivault/hashing.py) and then parsed with
    juce::MidiFile, so the plug-in plays what was indexed rather than whatever is under that name
    today.

    The source .mid is only ever opened for reading. Nothing in this class writes, renames or
    touches the file, which is the same rule the Python service runs under.

    There is deliberately no re-encode API. JUCE's reader closes every note the source left open
    (juce_MidiFile.cpp: readNextTrack -> updateMatchedPairs), and measured across the demo library
    each pass adds the same number of note-offs again -- Funk Bassline F goes 149, 170, 191, 212 --
    so a round trip inflates without ever settling. Anything a host receives must be the source
    bytes copied, not this parse written back out. VaultMidiTest.cpp pins that measurement. */
class MidiSource
{
public:
    /** Reads, hashes and parses. On failure, loaded() is false and errorMessage() says why. */
    bool load (const juce::String& filePath);

    void clear();

    bool loaded() const noexcept            { return isLoaded; }
    int  numTracks() const noexcept         { return file.getNumTracks(); }
    int  timeFormat() const noexcept        { return file.getTimeFormat(); }
    juce::int64 bytes() const noexcept      { return numBytes; }

    const juce::MidiFile& midiFile() const noexcept { return file; }
    const juce::MidiMessageSequence* track (int index) const { return file.getTrack (index); }

    /** Lowercase hex SHA-256 of the content last read. */
    juce::String contentHash() const        { return hash; }
    juce::String errorMessage() const       { return error; }

    HashCheck checkAgainst (const juce::String& recordedHash) const;

private:
    juce::MidiFile file;
    juce::String hash;
    juce::String error;
    juce::int64 numBytes = 0;
    bool isLoaded = false;
};

} // namespace vault

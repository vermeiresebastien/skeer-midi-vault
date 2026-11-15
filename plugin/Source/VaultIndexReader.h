#pragma once

#include <juce_core/juce_core.h>

#include <vector>

struct sqlite3;

namespace vault
{

/** The schema this build knows how to read. It is the app's own number, copied
    (midivault/engine/versions.py: SCHEMA_VERSION), and it is the reason the copy has to be
    checked: an index from a newer app is refused rather than half-understood. */
constexpr int supportedSchemaVersion = 2;

/** What a library is, as the index describes it. Only the columns the plug-in can act on. */
struct LibraryEntry
{
    juce::String path;
    juce::String filename;
    juce::String instrument;
    juce::String role;
    double tempoBpm = 0;
    double durationBeats = 0;
    double durationSeconds = 0;
    int noteCount = 0;
    int trackCount = 0;
    bool favorite = false;

    /** SHA-256 of the file's whole content, as the scanner recorded it (midivault/hashing.py).
        The plug-in needs it because the path alone is not the library: a file edited or
        replaced since the last scan is a different piece of music wearing the same name, and
        the only way to know is to hash what is on disk and compare. */
    juce::String contentHash;
};

/** A read-only window onto the index the Python service owns.

    The rule this class exists to enforce: the service writes, the plug-in reads. Nothing here
    may mutate the index, and the open guards it twice -- SQLITE_OPEN_READONLY, then
    PRAGMA query_only -- and checks both by reading them back off the connection. The URI form
    ?mode=ro is deliberately not used: a Windows path through SQLite's URI parser needs hand
    percent-encoding, and immutable=1 is forbidden outright, because measured against a live
    index it silently returned a stale page. */
class IndexReader
{
public:
    IndexReader();
    ~IndexReader();

    IndexReader (const IndexReader&) = delete;
    IndexReader& operator= (const IndexReader&) = delete;

    /** Opens read-only and reads the version. On failure, opened() is false and errorMessage()
        says why in terms a user can act on. */
    bool open (const juce::String& indexFile);

    void close();

    bool opened() const noexcept        { return database != nullptr; }
    int  schemaVersion() const noexcept { return schema; }
    juce::String errorMessage() const   { return error; }
    juce::String journalMode() const    { return journal; }

    /** Count of rows a user would call a usable file: indexed, and not marked missing. */
    long long countUsableFiles();

    /** The files a browser would list, favourites first then by name, capped by the caller. */
    std::vector<LibraryEntry> listFiles (int limit, const juce::String& textFilter);

    /** True when this connection could write. It should never be. */
    bool isWriteable();

private:
    bool execute (const juce::String& sql);

    sqlite3* database = nullptr;
    int schema = 0;
    juce::String error;
    juce::String journal;
};

} // namespace vault

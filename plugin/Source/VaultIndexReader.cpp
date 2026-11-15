#include "VaultIndexReader.h"

#include "sqlite3.h"

namespace vault
{

namespace
{

juce::String text (sqlite3_stmt* statement, int column)
{
    auto* value = sqlite3_column_text (statement, column);
    return value != nullptr ? juce::String (reinterpret_cast<const char*> (value)) : juce::String();
}

} // namespace

IndexReader::IndexReader() = default;

IndexReader::~IndexReader()
{
    close();
}

bool IndexReader::execute (const juce::String& sql)
{
    char* message = nullptr;

    if (sqlite3_exec (database, sql.toRawUTF8(), nullptr, nullptr, &message) != SQLITE_OK)
    {
        error = message != nullptr ? juce::String (message) : "SQLite refused \"" + sql + "\"";
        sqlite3_free (message);
        return false;
    }

    return true;
}

bool IndexReader::open (const juce::String& indexFile)
{
    close();

    if (! juce::File (indexFile).existsAsFile())
    {
        error = "There is no index at " + indexFile;
        return false;
    }

    // No URI here on purpose. SQLITE_OPEN_READONLY is the same thing mode=ro asks for, and a
    // Windows path fed through SQLite's URI parser has to be percent-encoded by hand -- one
    // '#' or '[' in a library folder and the open fails for a reason no user could guess.
    // immutable=1 stays unmentioned because it is forbidden: measured on a live index, it read
    // an out-of-date page and reported 8 files where 9 existed, silently.
    if (sqlite3_open_v2 (indexFile.toRawUTF8(), &database,
                         SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX, nullptr) != SQLITE_OK)
    {
        // The extended code is the part that can be acted on: SQLITE_CANTOPEN/PERM and
        // /DIR_NOT_FOUND are different advice for a user, and sqlite3_errmsg alone says
        // "unable to open database file" for all of them.
        const auto code = database != nullptr ? sqlite3_extended_errcode (database) : 0;

        error = (database != nullptr ? juce::String (sqlite3_errmsg (database))
                                     : "SQLite could not open " + indexFile)
                + " (code " + juce::String (code) + ")";
        close();
        return false;
    }

    // A scan holds the write lock; the plug-in waits rather than failing. Nothing here runs on
    // the audio thread -- see the rule in VaultMIDIProcessor about where SQLite may be touched.
    sqlite3_busy_timeout (database, 2000);

    if (sqlite3_db_readonly (database, "main") != 1)
    {
        error = "the connection came up writeable, which this plug-in must never have";
        close();
        return false;
    }

    if (! execute ("PRAGMA query_only=ON"))
    {
        close();
        return false;
    }

    error.clear();

    // meta.schema_version wins over PRAGMA user_version, exactly as it does in db.py; an index
    // with neither predates versioning and is treated as the oldest one this build understands.
    {
        sqlite3_stmt* statement = nullptr;

        if (sqlite3_prepare_v2 (database, "SELECT value FROM meta WHERE key='schema_version'",
                                -1, &statement, nullptr) == SQLITE_OK)
        {
            if (sqlite3_step (statement) == SQLITE_ROW)
                schema = text (statement, 0).getIntValue();

            sqlite3_finalize (statement);
        }
    }

    if (schema <= 0)
    {
        sqlite3_stmt* statement = nullptr;

        if (sqlite3_prepare_v2 (database, "PRAGMA user_version", -1, &statement, nullptr) == SQLITE_OK)
        {
            if (sqlite3_step (statement) == SQLITE_ROW)
                schema = sqlite3_column_int (statement, 0);

            sqlite3_finalize (statement);
        }
    }

    {
        sqlite3_stmt* statement = nullptr;

        if (sqlite3_prepare_v2 (database, "PRAGMA journal_mode", -1, &statement, nullptr) == SQLITE_OK)
        {
            if (sqlite3_step (statement) == SQLITE_ROW)
                journal = text (statement, 0);

            sqlite3_finalize (statement);
        }
    }

    if (schema > supportedSchemaVersion)
    {
        error = "This index was written by a newer SKEER MIDI VAULT (schema "
                + juce::String (schema) + ", this plug-in understands "
                + juce::String (supportedSchemaVersion) + "). Update the plug-in; the index "
                "will not be modified.";
        close();
        return false;
    }

    // The one table every readable index has. Anything else is some other program's database.
    {
        sqlite3_stmt* statement = nullptr;

        const auto sql = "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('files','tracks')";

        if (sqlite3_prepare_v2 (database, sql, -1, &statement, nullptr) != SQLITE_OK)
        {
            error = juce::String (sqlite3_errmsg (database));
            close();
            return false;
        }

        const bool hasTables = sqlite3_step (statement) == SQLITE_ROW
                               && sqlite3_column_int (statement, 0) == 2;
        sqlite3_finalize (statement);

        if (! hasTables)
        {
            error = indexFile + " is not a SKEER MIDI VAULT index: it has no files or tracks table";
            close();
            return false;
        }
    }

    return true;
}

void IndexReader::close()
{
    if (database != nullptr)
    {
        // Measured, because the obvious assumption is wrong: closing the last connection does
        // NOT remove the -shm and the empty -wal that a read-only open creates. Only a
        // writeable connection does the final checkpoint and unlinks them. What is left is a
        // 0-byte log -- no frame was ever written -- and a shared-memory map SQLite rebuilds,
        // and the app's own writer reuses both. tests/VaultIndexTest.cpp pins this down.
        sqlite3_close (database);
        database = nullptr;
    }

    schema = 0;
    journal.clear();
}

bool IndexReader::isWriteable()
{
    if (database == nullptr)
        return false;

    if (sqlite3_db_readonly (database, "main") != 1)
        return true;

    // Read back from the connection rather than assumed, because this method exists to catch a
    // build in which the guard stopped being set. The proof that a write actually fails is in
    // tests/VaultIndexTest.cpp, where it can be attempted without endangering a user's index.
    sqlite3_stmt* statement = nullptr;
    bool refusesWrites = false;

    if (sqlite3_prepare_v2 (database, "PRAGMA query_only", -1, &statement, nullptr) == SQLITE_OK)
    {
        if (sqlite3_step (statement) == SQLITE_ROW)
            refusesWrites = sqlite3_column_int (statement, 0) != 0;

        sqlite3_finalize (statement);
    }

    return ! refusesWrites;
}

long long IndexReader::countUsableFiles()
{
    if (database == nullptr)
        return -1;

    sqlite3_stmt* statement = nullptr;

    const auto sql = "SELECT count(*) FROM files WHERE indexed_at IS NOT NULL AND is_missing = 0";

    if (sqlite3_prepare_v2 (database, sql, -1, &statement, nullptr) != SQLITE_OK)
    {
        error = juce::String (sqlite3_errmsg (database));
        return -1;
    }

    long long count = -1;

    if (sqlite3_step (statement) == SQLITE_ROW)
        count = sqlite3_column_int64 (statement, 0);
    else
        error = juce::String (sqlite3_errmsg (database));

    sqlite3_finalize (statement);
    return count;
}

std::vector<LibraryEntry> IndexReader::listFiles (int limit, const juce::String& textFilter)
{
    std::vector<LibraryEntry> entries;

    if (database == nullptr)
        return entries;

    const auto sql = "SELECT path, filename, instrument, role, tempo_bpm, duration_beats,"
                     "       duration_seconds, note_count, track_count, favorite, content_hash"
                     "  FROM files"
                     " WHERE indexed_at IS NOT NULL AND is_missing = 0"
                     "   AND (? = '' OR filename LIKE '%' || ? || '%' OR path LIKE '%' || ? || '%')"
                     " ORDER BY favorite DESC, filename COLLATE NOCASE ASC"
                     " LIMIT ?";

    sqlite3_stmt* statement = nullptr;

    if (sqlite3_prepare_v2 (database, sql, -1, &statement, nullptr) != SQLITE_OK)
    {
        error = juce::String (sqlite3_errmsg (database));
        return entries;
    }

    // Bound, never concatenated: the filter is whatever someone types into the plug-in's
    // search box, and it reaches a database the user's corrections live in.
    sqlite3_bind_text (statement, 1, textFilter.toRawUTF8(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text (statement, 2, textFilter.toRawUTF8(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text (statement, 3, textFilter.toRawUTF8(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int  (statement, 4, limit);

    while (sqlite3_step (statement) == SQLITE_ROW)
    {
        LibraryEntry entry;
        entry.path           = text (statement, 0);
        entry.filename       = text (statement, 1);
        entry.instrument     = text (statement, 2);
        entry.role           = text (statement, 3);
        entry.tempoBpm       = sqlite3_column_double (statement, 4);
        entry.durationBeats  = sqlite3_column_double (statement, 5);
        entry.durationSeconds = sqlite3_column_double (statement, 6);
        entry.noteCount      = sqlite3_column_int (statement, 7);
        entry.trackCount     = sqlite3_column_int (statement, 8);
        entry.favorite       = sqlite3_column_int (statement, 9) != 0;
        entry.contentHash    = text (statement, 10);
        entries.push_back (std::move (entry));
    }

    sqlite3_finalize (statement);
    return entries;
}

} // namespace vault

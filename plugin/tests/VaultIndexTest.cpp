// The read-only path into the user's index, checked against a fixture this program builds and,
// when one exists, against the real index too.
//
// What is being proven is not "the query returns rows". Three things, each of which can go
// wrong in a way no other check in this tree can see:
//
//   1. No write gets through, even to a file this plug-in has open. Proven by hashing the
//      fixture before and after the whole read session -- a green run cannot then be a reader
//      that merely forgot to commit anything. And by checking that the only new files in the
//      folder are the -wal and -shm SQLite needs to read a WAL index at all, with no frame in
//      the log: a read-only connection cannot do the closing checkpoint that unlinks them, so
//      "no sidecars appear" was measured to be impossible and is not what is claimed here.
//   2. An index being written right now is read correctly. The app's scan holds the write lock
//      and the newest rows live in the -wal, which is the state a plug-in will normally meet.
//      immutable=1 was measured returning a stale page in exactly this state.
//   3. An index this build does not understand is refused with a sentence, not a crash and not
//      a half-populated browser.

#include <juce_core/juce_core.h>
#include <juce_cryptography/juce_cryptography.h>

#include <cstdio>
#include <vector>

#include "VaultIndexLocator.h"
#include "VaultIndexReader.h"
#include "sqlite3.h"

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

juce::String sha (const juce::File& file)
{
    return file.existsAsFile() ? juce::SHA256 (file).toHexString() : juce::String();
}

void reportSidecars (const juce::File& sandbox, const juce::String& when)
{
    std::printf ("info  %s: -wal %s (%lld), -shm %s (%lld)\n",
                 when.toRawUTF8(),
                 sandbox.getChildFile ("midivault.sqlite3-wal").existsAsFile() ? "present" : "gone",
                 static_cast<long long> (sandbox.getChildFile ("midivault.sqlite3-wal").getSize()),
                 sandbox.getChildFile ("midivault.sqlite3-shm").existsAsFile() ? "present" : "gone",
                 static_cast<long long> (sandbox.getChildFile ("midivault.sqlite3-shm").getSize()));
}

/** Child names in a folder, so "what did the read session leave behind" is a comparison of two
    lists rather than a hope about one file. */
juce::StringArray childNames (const juce::File& folder)
{
    const auto children = folder.findChildFiles (juce::File::findFiles
                                               | juce::File::findDirectories, false);

    juce::StringArray names;

    for (const auto& child : children)
        names.add (child.getFileName());

    names.sort (false);
    return names;
}

/** The two files SQLite makes in order to read a WAL-mode index at all: the write-ahead log it
    has to look for, and the shared-memory map that says where the last commit is. Nothing else
    may turn up in the user's folder because a plug-in glanced at their library. */
bool onlyTheWalPair (const juce::StringArray& names)
{
    for (const auto& name : names)
        if (! name.equalsIgnoreCase ("midivault.sqlite3-wal")
          && ! name.equalsIgnoreCase ("midivault.sqlite3-shm"))
            return false;

    return true;
}

/** What files.content_hash is allowed to hold: nothing, or SHA-256 in the exact shape
    hashlib.sha256(...).hexdigest() writes it -- 64 characters of lowercase hex. Not a shape this
    plug-in invented; it is the app's convention, and it is what makes a digest from the index
    comparable with one computed from the bytes. */
bool isAnAppDigest (const juce::String& hash)
{
    if (hash.isEmpty())
        return true;

    if (hash.length() != 64)
        return false;

    for (auto* c = hash.toRawUTF8(); *c != 0; ++c)
    {
        const bool hex = (*c >= '0' && *c <= '9') || (*c >= 'a' && *c <= 'f');

        if (! hex)
            return false;
    }

    return true;
}

/** Runs one statement on a writeable connection. A fixture that did not build is not a result,
    so this stops the run rather than letting the reader report on an empty folder. */
bool mustExec (sqlite3* database, const char* sql)
{
    char* message = nullptr;

    if (sqlite3_exec (database, sql, nullptr, nullptr, &message) == SQLITE_OK)
        return true;

    std::printf ("FAIL  the fixture could not run \"%s\": %s\n", sql,
                 message != nullptr ? message : "no message");
    sqlite3_free (message);
    return false;
}

/** The columns the reader touches, not the app's full table: a fixture that carried all
    eighty would only prove that copying db.py can be automated. */
const char* fixtureSchema =
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
    "CREATE TABLE files ("
    "  id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL DEFAULT '',"
    "  instrument TEXT, role TEXT, tempo_bpm REAL, duration_beats REAL, duration_seconds REAL,"
    "  note_count INTEGER DEFAULT 0, track_count INTEGER DEFAULT 0,"
    "  favorite INTEGER NOT NULL DEFAULT 0, indexed_at TEXT, is_missing INTEGER NOT NULL DEFAULT 0,"
    "  content_hash TEXT);"
    "CREATE TABLE tracks (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL);";

/** Two digests the app really produced, over files tracked in fixtures/demo_library:
    Drums/Trap Hat Pattern 140.mid and Full Arrangements/Odd Meter 7-8.mid. They are here rather
    than made up because the shape of files.content_hash -- 64 lowercase hex, exactly as
    midivault/hashing.py writes it -- is part of what this test has to pin. VaultMidiTest computes
    the same two values from the bytes and agrees, and both were checked against sha256sum and
    Python's hashlib before either test was written. */
const juce::String kickHash     = "e2ed4446abfff1ff9ce87d877ff0f95196b6b6792b32c821d2a618601e077d81";
const juce::String favouriteHash = "7f31e2b29370590ab41a27350642e8f05d4ab550ccd7db7bda5e08125510700a";

/** A writer standing in for the running service: it holds its connection open, so the rows it
    added stay in the -wal and nothing is checkpointed. */
class LiveWriter
{
public:
    ~LiveWriter()
    {
        if (database != nullptr)
            sqlite3_close (database);
    }

    bool open (const juce::File& file, int schemaVersion)
    {
        if (sqlite3_open_v2 (file.getFullPathName().toRawUTF8(), &database,
                             SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nullptr) != SQLITE_OK)
        {
            std::printf ("FAIL  could not create the fixture: %s\n", sqlite3_errmsg (database));
            return false;
        }

        return mustExec (database, "PRAGMA journal_mode=WAL")
            && mustExec (database, fixtureSchema)
            && mustExec (database, ("INSERT INTO meta(key,value) VALUES ('schema_version','"
                                    + juce::String (schemaVersion) + "')").toRawUTF8());
    }

    struct Row
    {
        juce::String path, filename, instrument;
        double tempo = 0;
        int notes = 0;
        bool favourite = false, indexed = true, missing = false;

        /** What the scanner recorded for these bytes, or empty for a row it never got to hash.
            Last so the rows written below stay readable. */
        juce::String hash;
    };

    bool add (const Row& row)
    {
        sqlite3_stmt* statement = nullptr;

        const char* insert =
            "INSERT INTO files(path,filename,instrument,role,tempo_bpm,duration_beats,"
            "duration_seconds,note_count,track_count,favorite,indexed_at,is_missing,content_hash)"
            " VALUES (?,?,?,?,?,0,0,?,?,?,CASE WHEN ? THEN '2026-11-15T00:00:00' ELSE NULL END,?,?)";

        if (sqlite3_prepare_v2 (database, insert, -1, &statement, nullptr) != SQLITE_OK)
        {
            std::printf ("FAIL  could not prepare an insert: %s\n", sqlite3_errmsg (database));
            return false;
        }

        sqlite3_bind_text  (statement, 1, row.path.toRawUTF8(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text  (statement, 2, row.filename.toRawUTF8(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text  (statement, 3, row.instrument.toRawUTF8(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text  (statement, 4, "drums", -1, SQLITE_TRANSIENT);
        sqlite3_bind_double (statement, 5, row.tempo);
        sqlite3_bind_int   (statement, 6, row.notes);
        sqlite3_bind_int   (statement, 7, 1);
        sqlite3_bind_int   (statement, 8, row.favourite ? 1 : 0);
        sqlite3_bind_int   (statement, 9, row.indexed ? 1 : 0);
        sqlite3_bind_int   (statement, 10, row.missing ? 1 : 0);

        // NULL, not '': midivault/db.py writes content_hash as a nullable column, and a row the
        // scanner never hashed has to reach the plug-in as "nothing recorded" rather than as a
        // value that happens to compare equal to something.
        if (row.hash.isEmpty())
            sqlite3_bind_null (statement, 11);
        else
            sqlite3_bind_text (statement, 11, row.hash.toRawUTF8(), -1, SQLITE_TRANSIENT);

        const bool ok = sqlite3_step (statement) == SQLITE_DONE;

        if (! ok)
            std::printf ("FAIL  could not insert %s: %s\n", row.filename.toRawUTF8(),
                         sqlite3_errmsg (database));

        sqlite3_finalize (statement);
        return ok;
    }

private:
    sqlite3* database = nullptr;
};

} // namespace

int main()
{
    std::printf ("SKEER MIDI VAULT index reader test\n================================\n\n");

    const auto sandbox = juce::File::getSpecialLocation (juce::File::currentExecutableFile)
                             .getParentDirectory().getChildFile ("midivault-index-sandbox");

    sandbox.deleteRecursively();
    sandbox.createDirectory();

    info ("sandbox: " + sandbox.getFullPathName());

    const auto indexFile = sandbox.getChildFile ("midivault.sqlite3");
    const auto walFile   = sandbox.getChildFile ("midivault.sqlite3-wal");

    {
        LiveWriter writer;

        if (! writer.open (indexFile, vault::supportedSchemaVersion))
            return 1;

        writer.add ({ "D:/MIDI/Drums/kick 808.mid",  "kick 808.mid",      "Kick",  128.0, 16,
                      false, true, false, kickHash });
        writer.add ({ "D:/MIDI/Drums/snare#7.mid",   "snare#7.mid",       "Snare", 140.0, 8  });
        writer.add ({ "D:/MIDI/It's a trap.mid",     "It's a trap.mid",   "Perc",  100.0, 64,
                      true, true, false, favouriteHash });
        writer.add ({ "D:/MIDI/not yet scanned.mid", "not yet scanned.mid", {},     0.0,   0,  false, false });
        writer.add ({ "D:/MIDI/gone missing.mid",    "gone missing.mid",  "Hat",   90.0,  4,  false, true, true });

        // Checkpointing is what a -wal is for: these rows exist only in it, so a reader that
        // ignored the log -- which is exactly what immutable=1 does -- sees an empty library.
        std::printf ("info  -wal present with the writer open: %s (%lld bytes)\n",
                     walFile.existsAsFile() ? "yes" : "no",
                     static_cast<long long> (walFile.getSize()));

        vault::IndexReader reader;
        const bool opened = reader.open (indexFile.getFullPathName());

        if (! opened)
            info ("open error: " + reader.errorMessage());

        check (opened, "opens an index another connection is writing to right now");
        check (reader.schemaVersion() == vault::supportedSchemaVersion,
               "reports the schema version the app stored, not its own guess");
        check (reader.journalMode().equalsIgnoreCase ("wal"), "and names the journal mode it found");
        check (! reader.isWriteable(), "the connection it opened cannot write");

        const long long usable = reader.countUsableFiles();

        std::printf ("info  usable files: %lld of 5 rows written\n", usable);
        check (usable == 3, "a row never indexed and a row marked missing are not counted as a library");

        const auto everything = reader.listFiles (50, {});

        check (static_cast<int> (everything.size()) == usable,
               "the listing agrees with the count, so a browser cannot quietly show a short list");
        check (! everything.empty() && everything.front().filename == "It's a trap.mid",
               "a favourite sorts to the front and an apostrophe survives the round trip");
        check (! everything.empty() && everything.front().tempoBpm == 100.0,
               "and the numbers arrive as numbers, not as text the caller has to parse");

        /** content_hash is the column that decides whether the bytes under a name are still the
            bytes the library described, so the plug-in reads it on every row it lists. It has to
            survive two ways of being lost: mangled on the way out, which breaks matching, and
            flattened from NULL to "", which would let two unhashed rows match each other. */
        const auto named = [&everything] (const juce::String& filename) -> const vault::LibraryEntry*
        {
            for (const auto& entry : everything)
                if (entry.filename == filename)
                    return &entry;

            return nullptr;
        };

        const auto* hashed = named ("kick 808.mid");
        const auto* unhashed = named ("snare#7.mid");

        check (hashed != nullptr && hashed->contentHash == kickHash,
               "a row's digest arrives byte for byte: "
               + (hashed != nullptr ? hashed->contentHash : juce::String ("<row missing>")));

        check (unhashed != nullptr && unhashed->contentHash.isEmpty(),
               "and a row the scanner never hashed arrives empty, so it can be called unknown "
               "instead of matching another empty string");

        const auto onlyKicks = reader.listFiles (50, "kick");
        check (onlyKicks.size() == 1 && onlyKicks.front().instrument == "Kick",
               "a text filter narrows the list to what it names");

        const auto hostile = reader.listFiles (50, "x' OR 1=1 --");
        check (hostile.empty(), "a filter is data: injecting through it matches rows for nobody");

        check (reader.listFiles (2, {}).size() == 2,
               "the caller's cap holds, so a 46,000-file index cannot freeze a GUI frame");

        // The state a plug-in actually meets: someone scans while the session is open. A
        // connection that snapshotted at open, or read around the log, would still say three.
        writer.add ({ "D:/MIDI/added mid-session.mid", "added mid-session.mid", "Ride", 122.0, 12 });

        const long long afterScan = reader.countUsableFiles();

        std::printf ("info  usable files after the writer added one: %lld\n", afterScan);
        check (afterScan == 4, "a row written after this connection opened is there on the next query");

        reader.close();

        check (! reader.opened() && reader.countUsableFiles() == -1,
               "after close it holds nothing, and says so instead of returning a stale count");
    }

    //=========================================================================
    // A quiet index: everything a read session must not do
    //=========================================================================
    {
        // The writer has closed, so the -wal is checkpointed away and the file is still again.
        // Hashing before this point would compare a file the *writer* was about to change.
        const auto quietBefore = sha (indexFile);
        const auto childrenBefore = childNames (sandbox);

        std::printf ("info  quiet index sha before: %s\n", quietBefore.substring (0, 24).toRawUTF8());
        reportSidecars (sandbox, "after the writer closed");

        vault::IndexReader reader;

        if (reader.open (indexFile.getFullPathName()))
        {
            reader.countUsableFiles();
            reader.listFiles (50, "kick");
            reader.close();
        }
        else
        {
            check (false, "the quiet index opens: " + reader.errorMessage());
        }

        const auto quietAfter = sha (indexFile);

        std::printf ("info  quiet index sha after:  %s\n", quietAfter.substring (0, 24).toRawUTF8());
        reportSidecars (sandbox, "after the quiet read session");

        check (quietBefore.isNotEmpty() && quietBefore == quietAfter,
               "a whole read session leaves the index byte for byte alone");

        // Measured, not assumed: a read-only connection cannot do the closing checkpoint that
        // unlinks the sidecars, so "and leaves no -wal or -shm behind" is a claim SQLite makes
        // impossible and it failed for 1050 ms of waiting. What is still falsifiable, and what
        // actually protects the user, is (a) nothing else appears in the folder and (b) the log
        // that does appear holds no frame -- a reader that wrote would be caught here.
        const auto childrenAfter = childNames (sandbox);

        juce::StringArray grew;

        for (const auto& name : childrenAfter)
            if (! childrenBefore.contains (name))
                grew.add (name);

        info ("new files in the folder after the read session: " + grew.joinIntoString (", "));

        check (onlyTheWalPair (grew),
               "and nothing but the -wal and -shm SQLite needs to read a WAL index appears "
               "in the user's folder");

        const long long walBytes = walFile.existsAsFile() ? walFile.getSize() : 0;

        std::printf ("info  -wal left behind holds %lld bytes\n", walBytes);
        check (walBytes == 0,
               "and the log it leaves behind holds no frame: the plug-in wrote nothing");
    }

    //=========================================================================
    // The schema that is actually on this machine right now
    //=========================================================================
    {
        // Read off %LOCALAPPDATA%\Skeer\MIDI Vault\midivault.sqlite3 on 2026-11-15: its meta
        // table says schema_version '1' while db.py now writes 2, because that library has not
        // been opened by the app since the migration steps landed. So a plug-in that only
        // understood 2 would hand an empty browser to anyone who has not relaunched the app.
        // Schema 1 is not hypothetical here -- it is the state this reader has to serve today.
        const auto legacy = sandbox.getChildFile ("legacy").getChildFile ("midivault.sqlite3");
        legacy.getParentDirectory().createDirectory();

        LiveWriter old;

        if (! old.open (legacy, 1))
        {
            check (false, "the schema 1 fixture could not be built");
        }
        else
        {
            old.add ({ "D:/MIDI/Drums/old kick.mid", "old kick.mid", "Kick", 124.0, 32 });

            vault::IndexReader reader;

            if (! reader.open (legacy.getFullPathName()))
            {
                check (false, "a schema 1 index opens, because that is what is on this machine: "
                              + reader.errorMessage());
            }
            else
            {
                check (reader.schemaVersion() == 1,
                       "a schema 1 index is read, not refused, and names the version it found");
                check (reader.countUsableFiles() == 1,
                       "and the library behind it arrives instead of reading as an empty browser");
                reader.close();
            }
        }
    }

    //=========================================================================
    // What it refuses
    //=========================================================================
    {
        vault::IndexReader reader;

        check (! reader.open (indexFile.getParentDirectory().getChildFile ("nothing.sqlite3").getFullPathName())
                   && reader.errorMessage().isNotEmpty(),
               "a path with no index in it is refused with a reason, not silence");

        const auto junk = sandbox.getChildFile ("junk.sqlite3");
        junk.replaceWithData ("this is not a database, it is a shopping list", 43);

        vault::IndexReader notADatabase;
        const bool junkOpened = notADatabase.open (junk.getFullPathName());

        // The message is read only after open() has returned. Building the label inside the
        // call meant an argument that could be evaluated first, and a passing check whose
        // printed reason was empty.
        check (! junkOpened && notADatabase.errorMessage().isNotEmpty(),
               "a file that is not an index is refused: " + notADatabase.errorMessage());

        const auto newer = sandbox.getChildFile ("newer").getChildFile ("midivault.sqlite3");
        newer.getParentDirectory().createDirectory();   // SQLite will not make a folder for you

        LiveWriter future;

        if (future.open (newer, vault::supportedSchemaVersion + 7))
        {
            future.add ({ "D:/MIDI/from next year.mid", "from next year.mid", "Kick", 120.0, 8 });

            vault::IndexReader refused;
            const bool rejected = ! refused.open (newer.getFullPathName());

            info ("refusal says: " + refused.errorMessage());

            check (rejected && refused.errorMessage().containsIgnoreCase ("newer"),
                   "an index from a newer app is refused, and says which is which");
            check (refused.countUsableFiles() == -1 && ! refused.opened(),
                   "and nothing is read from it: no partial library behind the refusal");
        }
        else
        {
            skip ("could not build a newer-schema fixture, so the refusal was not exercised");
        }
    }

    //=========================================================================
    // The real index, if this machine has one
    //=========================================================================
    {
        const auto realFile = vault::resolveIndex (vault::IndexRoots::fromRuntime());

        if (realFile.isEmpty())
        {
            skip ("no SKEER MIDI VAULT index is installed on this machine, "
                  "so the live index was not read");
        }
        else
        {
            // A WAL index needs to create -shm the moment it is opened, even read-only. Where
            // the folder will not allow that, SQLite says only "unable to open database file",
            // which would otherwise read as a broken reader. So the folder is tried first, and
            // a refusal to write it is reported as the reason the live index is not being read.
            const juce::File liveDirectory = juce::File (realFile).getParentDirectory();
            const juce::File probe = liveDirectory.getChildFile ("midivault-reader-probe.tmp");

            const bool writable = probe.replaceWithData ("x", 1);

            if (writable)
                probe.deleteFile();

            if (! writable)
            {
                skip ("the live index folder is not writable by this process, and SQLite needs "
                      "to create -shm there even for a read-only open: " + liveDirectory.getFullPathName());
            }
            else
            {
                const auto realBefore = sha (juce::File (realFile));

                info ("live index: " + realFile);

                vault::IndexReader live;

                if (! live.open (realFile))
                {
                    check (false, "the live index opens read-only: " + live.errorMessage());
                }
                else
                {
                    const long long count = live.countUsableFiles();
                    std::printf ("info  live schema=%d journal=%s usable=%lld\n",
                                 live.schemaVersion(), live.journalMode().toRawUTF8(), count);

                    check (count > 0, "the live index reports a library of some size: "
                           + juce::String (static_cast<long long> (count)) + " files");
                    check (! live.isWriteable(), "the live connection cannot write");

                    const auto firstTen = live.listFiles (10, {});
                    check (! firstTen.empty() && ! firstTen.front().path.isEmpty(),
                           "and the first page of the real library arrives with paths to read");

                    bool digestsLookLikeDigests = true;
                    int digestsCarried = 0;

                    for (const auto& entry : firstTen)
                    {
                        if (! entry.contentHash.isEmpty())
                            ++digestsCarried;

                        if (! isAnAppDigest (entry.contentHash))
                            digestsLookLikeDigests = false;
                    }

                    std::printf ("info  live rows carrying a digest: %d of %d\n",
                                 digestsCarried, static_cast<int> (firstTen.size()));

                    // Only the real index can answer this: the fixture proves what the reader does
                    // with a value, this proves the value the app actually writes is one the
                    // plug-in can compare against a SHA-256 of the bytes.
                    check (digestsCarried > 0 && digestsLookLikeDigests,
                           "every digest in the live library is 64 lowercase hex, the shape "
                           "hashlib.hexdigest() produces");

                    const auto search = live.listFiles (5, firstTen.empty() ? "a"
                                                                            : firstTen.front().filename);
                    check (! search.empty(),
                           "searching the live index for a file it just named finds it");

                    live.close();
                }

                check (sha (juce::File (realFile)) == realBefore,
                       "the user's own index is unchanged by all of that");

                std::printf ("info  sidecars left in the live folder: %s\n",
                             (juce::File (realFile).getParentDirectory()
                                  .getChildFile ("midivault.sqlite3-shm").existsAsFile()
                              || juce::File (realFile).getParentDirectory()
                                  .getChildFile ("midivault.sqlite3-wal").existsAsFile())
                                 ? "-shm or -wal still there" : "none");
            }
        }
    }

    sandbox.deleteRecursively();

    std::printf ("\n%d checks, %d failed, %d skipped\n", checks, failures, skipped);
    return failures > 0 ? 1 : 0;
}

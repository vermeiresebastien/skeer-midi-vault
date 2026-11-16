// The front door, driven directly: the editor a producer touches, built and exercised without a
// window, a display or a mouse.
//
// What this proves that no other suite here can:
//
//   1. createEditor() builds a real panel and the processor says it has one. Until step 6 it
//      returned nullptr, and the VST3 was a tested library in a plug-in's clothes.
//   2. Building the panel opens nothing. The index folder holds the index alone until Connect is
//      pressed -- so "the plug-in touched my data folder the moment the track loaded" is measured
//      to be false, not asserted.
//   3. Connect populates the list from an index this test wrote, and leaves the folder holding
//      only the -wal/-shm pair SQLite needs to read a WAL index at all. /wal is asserted as a
//      *diff*, not as an absence, because a read-only connection cannot do the checkpoint that
//      removes them (plugin/tests/VaultIndexTest.cpp:10-14).
//   4. The filter narrows the row set, a row click loads through the processor's one load path,
//      and the exported parameters stay attached and live afterwards.
//   5. A host-driven restore that cannot find its file leaves the panel saying which file the
//      project wanted and that it is not there -- and leaves the browser usable, because the panel
//      holds no open handle for a restore to invalidate.
//   6. "Save clip as..." writes exactly one new file, whose SHA-256 equals the source's, and
//      refuses the file that is playing, an empty source and an unconfirmed overwrite. The source
//      .mid is hashed again at the end of the run: nothing in this session may have written it.
//   7. The overwrite gate is the operating system's, and the panel asks for it -- so the callback
//      that replaces a file is answering a prompt a human already replied to, not a confirm box of
//      this build's own. (A box of this build's own was the review's critical finding: non-native
//      JUCE numbers its second button 0 and its first 1, so the old code replaced on Cancel.)
//   8. Two index states a producer actually meets -- nothing there, and something that is not an
//      index -- are said in the strip's own words, with the buttons that go with them, and a read
//      that fails does not throw away the connection the user asked for: Rescan is the retry and
//      Disconnect is the only click that forgets.
//   9. "Copy path" puts the clip's path on the real clipboard, read back through the same API, and
//      the note a save leaves behind is retired by the next click that changes what it would be
//      about.
//
// Deliberately absent: showTopLevelWindowOnScreen(), any peer, any desktop. The checks must not
// depend on a display and must not take focus from whatever the user has running.
//
// Exit code is the failure count clamped to 1, so ctest reads it directly.

#include <juce_cryptography/juce_cryptography.h>
#include <juce_gui_basics/juce_gui_basics.h>

#include <cstdio>
#include <cstdlib>
#include <memory>
#include <vector>

#include "VaultClipExport.h"
#include "VaultEditor.h"
#include "VaultIndexLocator.h"
#include "VaultIndexReader.h"
#include "sqlite3.h"

#ifndef SKEER_FIXTURE_DIR
 #define SKEER_FIXTURE_DIR ""
#endif

namespace
{

int checks = 0;
int failures = 0;

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

juce::String sha (const juce::File& file)
{
    return file.existsAsFile() ? juce::SHA256 (file).toHexString() : juce::String();
}

/** Child names in a folder, so "what did this session leave behind" is a comparison of two lists. */
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

juce::StringArray addedNames (const juce::StringArray& before, const juce::StringArray& after)
{
    juce::StringArray added;

    for (const auto& name : after)
        if (! before.contains (name))
            added.add (name);

    return added;
}

/** The two files SQLite makes in order to read a WAL-mode index at all. A read-only connection
    cannot remove them, so the claim made here is "nothing else appeared", not "nothing appeared". */
bool onlyTheWalPair (const juce::StringArray& names)
{
    for (const auto& name : names)
        if (! name.equalsIgnoreCase ("midivault.sqlite3-wal")
          && ! name.equalsIgnoreCase ("midivault.sqlite3-shm"))
            return false;

    return true;
}

/** A click, minus the OS event. The panel wires its buttons through onClick, and a headless check
    has no peer to deliver a mouse event to; the effect asserted afterwards is the click's own. */
bool click (juce::Button& button)
{
    if (button.onClick == nullptr)
        return false;

    button.onClick();
    return true;
}

template <typename T>
T* find (juce::Component& parent, const char* componentID)
{
    // Not recursive in JUCE, which is fine: every control this panel has is a direct child.
    return dynamic_cast<T*> (parent.findChildWithID (componentID));
}

/** juce::TextEditor::textChanged() posts a command message rather than calling its listener inline
    (juce_TextEditor.cpp:1304), so a check that "types" has to let a loop run before the panel has
    re-queried. A console program has no loop of its own; this borrows one long enough for the
    queued message to be dispatched, and no longer. */
void pumpMessages()
{
    juce::MessageManager::getInstance()->runDispatchLoopUntil (25);
}

/** The strip's note line -- the sentence the save and copy buttons write.
    
    Asking "what does the strip say about the save" has to be a question about one line, not a
    substring of the whole block: the block is several lines joined with \n, and a refusal that
    merely contains the words of the success sentence ("Not saved: the file at X is not
    byte-identical to the clip") would otherwise satisfy a test written as contains(). refreshStatus
    appends the note last, so the last line is the note whenever there is one. */
juce::String noteLine (const juce::String& strip)
{
    juce::StringArray lines;
    lines.addLines (strip);

    return lines.isEmpty() ? juce::String() : lines[lines.size() - 1].trim();
}

/** One row's index by the file it names, because the interesting rows here are named by what they
    are (the real clip, the 0-byte clip) rather than by the position they happen to sort into. */
int rowWithPath (const VaultEditor* panel, const juce::String& path)
{
    const auto& rows = panel->rows();

    for (size_t row = 0; row < rows.size(); ++row)
        if (rows[row].path == path)
            return static_cast<int> (row);

    return -1;
}

void setEnvironment (const juce::String& name, const juce::String& value)
{
   #if JUCE_WINDOWS
    _putenv_s (name.toRawUTF8(), value.toRawUTF8());
   #else
    setenv (name.toRawUTF8(), value.toRawUTF8(), 1);
   #endif
}

juce::String environment (const juce::String& name)
{
    return juce::SystemStats::getEnvironmentVariable (name, {});
}

/** A database at `path` holding `sql` and nothing else.

    This is how to make the second of the reader's two refusal sentences reachable: a file that is a
    real SQLite database but not a vault index. A text file wearing the name never gets there --
    sqlite3_exec refuses the reader's first PRAGMA, so the message that reaches the strip is
    SQLite's "file is not a database" (VaultIndexReader.cpp:81 through execute(), :32) and the
    table check at :158 is never run. Both sentences are asserted below, because they are advice for
    two different problems a user can have. */
bool makeDatabase (const juce::String& path, const char* sql)
{
    sqlite3* database = nullptr;

    if (sqlite3_open_v2 (path.toRawUTF8(), &database,
                         SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nullptr) != SQLITE_OK)
    {
        std::printf ("FAIL  could not create %s: %s\n", path.toRawUTF8(),
                     sqlite3_errmsg (database));
        sqlite3_close (database);
        return false;
    }

    char* message = nullptr;
    const bool ok = sqlite3_exec (database, sql, nullptr, nullptr, &message) == SQLITE_OK;

    if (! ok)
        std::printf ("FAIL  could not run the sql for %s: %s\n", path.toRawUTF8(),
                     message != nullptr ? message : "no message");

    sqlite3_free (message);
    sqlite3_close (database);
    return ok;
}

float paramValue (VaultMIDIProcessor& processor, const juce::String& id)
{
    if (auto* raw = processor.valueTreeState.getRawParameterValue (id))
        return raw->load();

    return -999.0f;
}

//==============================================================================
/** The columns the reader touches, exactly as plugin/tests/VaultIndexTest.cpp builds them: a
    fixture that carried all eighty columns would only prove that copying db.py can be automated. */
const char* fixtureSchema =
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
    "CREATE TABLE files ("
    "  id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL DEFAULT '',"
    "  instrument TEXT, role TEXT, tempo_bpm REAL, duration_beats REAL, duration_seconds REAL,"
    "  note_count INTEGER DEFAULT 0, track_count INTEGER DEFAULT 0,"
    "  favorite INTEGER NOT NULL DEFAULT 0, indexed_at TEXT, is_missing INTEGER NOT NULL DEFAULT 0,"
    "  content_hash TEXT);"
    "CREATE TABLE tracks (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL);";

class FixtureWriter
{
public:
    ~FixtureWriter()
    {
        if (database != nullptr)
            sqlite3_close (database);
    }

    bool open (const juce::File& file)
    {
        if (sqlite3_open_v2 (file.getFullPathName().toRawUTF8(), &database,
                             SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nullptr) != SQLITE_OK)
        {
            std::printf ("FAIL  could not create the fixture index: %s\n", sqlite3_errmsg (database));
            return false;
        }

        return exec ("PRAGMA journal_mode=WAL")
            && exec (fixtureSchema)
            && exec ("INSERT INTO meta(key,value) VALUES ('schema_version','2')");
    }

    bool add (const juce::String& path, const juce::String& filename, const juce::String& instrument,
              double tempoBpm, double durationBeats, int notes, bool favourite,
              const juce::String& contentHash)
    {
        sqlite3_stmt* statement = nullptr;

        const char* insert =
            "INSERT INTO files(path,filename,instrument,role,tempo_bpm,duration_beats,"
            "duration_seconds,note_count,track_count,favorite,indexed_at,is_missing,content_hash)"
            " VALUES (?,?,?,'drums',?,?,0,?,1,?,'2026-11-16T00:00:00',0,?)";

        if (sqlite3_prepare_v2 (database, insert, -1, &statement, nullptr) != SQLITE_OK)
        {
            std::printf ("FAIL  could not prepare an insert: %s\n", sqlite3_errmsg (database));
            return false;
        }

        sqlite3_bind_text   (statement, 1, path.toRawUTF8(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text   (statement, 2, filename.toRawUTF8(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text   (statement, 3, instrument.toRawUTF8(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_double (statement, 4, tempoBpm);
        sqlite3_bind_double (statement, 5, durationBeats);
        sqlite3_bind_int    (statement, 6, notes);
        sqlite3_bind_int    (statement, 7, favourite ? 1 : 0);

        if (contentHash.isEmpty())
            sqlite3_bind_null (statement, 8);
        else
            sqlite3_bind_text (statement, 8, contentHash.toRawUTF8(), -1, SQLITE_TRANSIENT);

        const bool ok = sqlite3_step (statement) == SQLITE_DONE;

        if (! ok)
            std::printf ("FAIL  could not insert %s: %s\n", filename.toRawUTF8(),
                         sqlite3_errmsg (database));

        sqlite3_finalize (statement);
        return ok;
    }

private:
    bool exec (const char* sql)
    {
        char* message = nullptr;

        if (sqlite3_exec (database, sql, nullptr, nullptr, &message) == SQLITE_OK)
            return true;

        std::printf ("FAIL  the fixture could not run \"%s\": %s\n", sql,
                     message != nullptr ? message : "no message");
        sqlite3_free (message);
        return false;
    }

    sqlite3* database = nullptr;
};

} // namespace

//==============================================================================
int main()
{
    juce::ScopedJuceInitialiser_GUI gui;

    std::printf ("SKEER MIDI VAULT editor test\n============================\n\n");

    const auto sandbox = juce::File::getSpecialLocation (juce::File::currentExecutableFile)
                             .getParentDirectory().getChildFile ("midivault-editor-sandbox");

    sandbox.deleteRecursively();
    sandbox.createDirectory();

    const auto libraryFolder = sandbox.getChildFile ("library");
    libraryFolder.createDirectory();

    info ("sandbox: " + sandbox.getFullPathName());

    // A real clip, not a name: a row whose path is not on disk cannot test a load, and the copy is
    // what the digest, the save and the "never write a source" checks are all about.
    const juce::File demoClip (juce::File (juce::String (SKEER_FIXTURE_DIR))
                                   .getChildFile ("Drums")
                                   .getChildFile ("Trap Hat Pattern 140.mid"));

    check (demoClip.existsAsFile(),
           "the demo library the browser will list is where the repo says it is");

    if (! demoClip.existsAsFile())
        return 1;

    const auto clip = libraryFolder.getChildFile ("Trap Hat Pattern 140.mid");
    check (demoClip.copyFileTo (clip), "a real .mid is copied into the sandbox library");

    const auto clipHash = sha (clip);
    info ("clip SHA-256: " + clipHash);

    // A clip that exists and has no bytes. It is a row in the index and a path on disk because that
    // is the state the export rule is about: a file can empty itself after the plug-in loaded it --
    // a half-synced drive, a truncated copy -- and the save that follows must refuse rather than
    // delete the file the user just named. juce_File.cpp:777 is why: a zero-length
    // File::replaceWithData is a deleteFile() wearing a write's name.
    const auto emptyClip = libraryFolder.getChildFile ("empty clip.mid");
    check (emptyClip.create().wasOk() && emptyClip.getSize() == 0,
           "a 0-byte .mid is in the sandbox library and the index lists it");

    const auto indexFile = libraryFolder.getChildFile ("midivault.sqlite3");

    {
        FixtureWriter writer;

        if (! writer.open (indexFile))
            return 1;

        const bool wrote = writer.add (clip.getFullPathName(), clip.getFileName(), "Hat", 140.0, 16.0,
                                       32, false, clipHash)
                        && writer.add (libraryFolder.getChildFile ("wont load.mid").getFullPathName(),
                                       "wont load.mid", "Hat", 0.0, 0.0, 0, false, {})
                        && writer.add (emptyClip.getFullPathName(), emptyClip.getFileName(), "Hat",
                                       0.0, 0.0, 0, false, sha (emptyClip))
                        && writer.add (libraryFolder.getChildFile ("Piano Sketch.mid").getFullPathName(),
                                       "Piano Sketch.mid", "Piano", 100.0, 8.0, 12, true, {});

        check (wrote, "the fixture index holds four rows: one real clip, one bad path, one 0-byte "
                      "clip, one favourite");
    }

    // The writer is closed, so its -wal has been checkpointed away and this is the state the panel
    // must leave untouched. Everything below compares against these two values.
    const auto indexHash         = sha (indexFile);
    const auto folderBeforeOpen  = childNames (libraryFolder);

    check (! libraryFolder.getChildFile ("midivault.sqlite3-shm").existsAsFile()
             && ! libraryFolder.getChildFile ("midivault.sqlite3-wal").existsAsFile(),
           "with no reader open the fixture folder holds the index alone, so the next diff means something");

    // Discovery, not a test-only door: the panel finds its index the way it does on the user's
    // machine, through the four roots, and SKEER_MIDIVAULT_DATA is first in that order.
    setEnvironment ("SKEER_MIDIVAULT_DATA", libraryFolder.getFullPathName());

    VaultMIDIProcessor processor;
    processor.setRateAndBufferSizeDetails (48000.0, 512);
    processor.prepareToPlay (48000.0, 512);

    std::unique_ptr<juce::AudioProcessorEditor> editor (processor.createEditor());

    check (processor.hasEditor(), "the processor reports that it has an editor");
    check (editor != nullptr && dynamic_cast<VaultEditor*> (editor.get()) != nullptr,
           "createEditor() builds the real panel, not a null pointer");

    if (editor == nullptr)
        return 1;

    editor->setSize (560, 640);

    //==========================================================================
    // The widget tree, before anything is pressed
    auto* connectButton    = find<juce::TextButton> (*editor, "vaultConnect");
    auto* rescanButton     = find<juce::TextButton> (*editor, "vaultRescan");
    auto* disconnectButton = find<juce::TextButton> (*editor, "vaultDisconnect");
    auto* copyPathButton   = find<juce::TextButton> (*editor, "vaultCopyPath");
    auto* saveAsButton     = find<juce::TextButton> (*editor, "vaultSaveAs");
    auto* filterBox        = find<juce::TextEditor> (*editor, "vaultFilter");
    auto* listBox          = find<juce::ListBox> (*editor, "vaultList");
    auto* statusLabel      = find<juce::Label> (*editor, "vaultStatus");
    auto* transposeSlider  = find<juce::Slider> (*editor, "vaultTranspose");
    auto* followTempoBox   = find<juce::ComboBox> (*editor, "vaultFollowTempo");
    auto* loopBox          = find<juce::ComboBox> (*editor, "vaultLoop");

    check (connectButton != nullptr && connectButton->getButtonText() == "Connect",
           "the panel has a Connect button");
    check (rescanButton != nullptr && disconnectButton != nullptr,
           "and Rescan and Disconnect beside it");
    check (filterBox != nullptr && listBox != nullptr && statusLabel != nullptr,
           "a filter box, a list and a status strip are all in the tree");
    check (transposeSlider != nullptr && followTempoBox != nullptr && loopBox != nullptr,
           "the three exported parameters are permanently on screen");
    check (copyPathButton != nullptr && saveAsButton != nullptr,
           "and the two non-drag exits from step 7 are buttons a user can see");

    if (connectButton == nullptr || filterBox == nullptr || listBox == nullptr
        || statusLabel == nullptr || transposeSlider == nullptr)
        return 1;

    check (connectButton->isEnabled() && ! rescanButton->isEnabled()
             && ! disconnectButton->isEnabled(),
           "before Connect the panel offers Connect and nothing else, because nothing is connected");
    check (! copyPathButton->isEnabled() && ! saveAsButton->isEnabled(),
           "and there is no clip to copy or save yet");

    check (dynamic_cast<VaultEditor*> (editor.get())->rows().empty(),
           "no rows are listed before Connect is pressed");
    check (statusLabel->getText().contains ("not connected"),
           "and the strip says so rather than showing an empty-looking library: "
           + statusLabel->getText());

    // The claim the product rule is about: a track loading into a host must not touch the user's
    // data folder. Built, laid out and given a timer, the panel has opened nothing.
    const auto folderAfterConstruction = childNames (libraryFolder);

    check (folderAfterConstruction == folderBeforeOpen,
           "constructing the panel opens nothing: the index folder is byte-for-byte the same list");
    check (sha (indexFile) == indexHash, "and the index file itself is unchanged by being built beside");

    //==========================================================================
    // Connect
    check (click (*connectButton), "the Connect button carries a click handler");
    check (dynamic_cast<VaultEditor*> (editor.get())->connectedIndex()
             .endsWithIgnoreCase ("midivault.sqlite3"),
           "a click on Connect finds the index through the locator: "
           + dynamic_cast<VaultEditor*> (editor.get())->connectedIndex());

    const auto rows = dynamic_cast<VaultEditor*> (editor.get())->rows();

    check (static_cast<int> (rows.size()) == 4,
           "and the list holds the four usable rows the index describes");
    check (listBox->getListBoxModel() != nullptr && listBox->getListBoxModel()->getNumRows() == 4,
           "the ListBox is wired to the panel, not merely next to a vector");
    check (! rows.empty() && rows.front().filename == "Piano Sketch.mid",
           "a favourite sorts to the front, as the query orders it");

    check (statusLabel->getText().contains (libraryFolder.getFullPathName()),
           "the strip names the index root it connected to");
    check (statusLabel->getText().contains ("SKEER_MIDIVAULT_DATA"),
           "and the place that root came from, so a second index is explainable");
    check (statusLabel->getText().contains ("4 usable files"),
           "and how many files a user would call usable");

    {
        const auto added = addedNames (folderBeforeOpen, childNames (libraryFolder));

        std::printf ("info  files connect added: %s\n", added.joinIntoString (", ").toRawUTF8());
        check (onlyTheWalPair (added) && added.size() == 2,
               "connecting leaves only the -wal and -shm a read-only open needs, and nothing else");
        check (sha (indexFile) == indexHash, "and the index is read, not written");
    }

    check (rescanButton->isEnabled() && disconnectButton->isEnabled() && ! connectButton->isEnabled(),
           "the buttons now name the only sensible next actions");

    //==========================================================================
    // The filter
    const int beforeFilter = listBox->getListBoxModel()->getNumRows();

    filterBox->setText ("Trap");
    pumpMessages();

    const auto filtered = dynamic_cast<VaultEditor*> (editor.get())->rows();

    check (static_cast<int> (filtered.size()) == 1 && ! filtered.empty()
             && filtered.front().filename == clip.getFileName(),
           "typing in the filter narrows the row set to what it names");
    check (listBox->getListBoxModel()->getNumRows() < beforeFilter,
           "and the list on screen shrinks with it");

    filterBox->setText ("");
    pumpMessages();

    check (static_cast<int> (dynamic_cast<VaultEditor*> (editor.get())->rows().size()) == 4,
           "clearing the filter brings the library back");

    //==========================================================================
    // Choosing a row
    auto* panel = dynamic_cast<VaultEditor*> (editor.get());

    int clipRow = -1;

    for (int row = 0; row < static_cast<int> (panel->rows().size()); ++row)
        if (panel->rows()[static_cast<size_t> (row)].path == clip.getFullPathName())
            clipRow = row;

    check (clipRow >= 0, "the fixture's real clip is one of the rows");

    if (clipRow >= 0)
        panel->chooseRow (clipRow);

    const auto afterLoad = processor.status();

    check (afterLoad.loaded && afterLoad.file == clip.getFullPathName(),
           "choosing a row loads the clip through the processor's one load path");
    check (statusLabel->getText().contains (clip.getFullPathName()),
           "and the strip names the file that is playing");
    check (statusLabel->getText().contains ("beats"),
           "and says how long it is in beats");

    check (transposeSlider->getValue() == 0.0 && transposeSlider->getMinimum() == -24.0
             && transposeSlider->getMaximum() == 24.0,
           "loading a clip leaves Transpose where the user left it (default 0, range -24..+24)");

    transposeSlider->setValue (5.0, juce::sendNotificationSync);

    // getRawParameterValue hands out the parameter's own units, not the 0..1 the host speaks:
    // -24..+24 is stored as -24..+24 (juce_AudioProcessorValueTreeState.cpp, getRawParameterValue).
    check (std::abs (paramValue (processor, VaultMIDIProcessor::transposeId) - 5.0f) < 0.001f,
           "and the attachment is live: moving the panel's slider moves the parameter the audio "
           "thread reads");

    //==========================================================================
    // The 0-byte clip: a row that is really there, and what picking it may and may not claim
    {
        const auto emptyRow = rowWithPath (panel, emptyClip.getFullPathName());

        check (emptyRow >= 0, "the 0-byte clip is one of the rows the browser lists");

        const auto sandboxBeforePick = childNames (sandbox);

        panel->chooseRow (emptyRow);

        const auto afterEmptyPick = processor.status();

        // Measured against VaultMidiSource::load, not assumed: a file with no bytes fails to parse,
        // and VaultMIDIProcessor::load leaves the clip that was already playing alone when a pick
        // goes wrong. So the honest sentence here is "still playing the good clip, and this other
        // file would not open" -- which is what the strip has to say, and the reason the export
        // refusal below cannot be reached through a pick.
        check (afterEmptyPick.loaded && afterEmptyPick.file == clip.getFullPathName(),
               "picking the 0-byte row does not make it the playing clip");
        check (statusLabel->getText().contains (emptyClip.getFileName())
                 && statusLabel->getText().containsIgnoreCase ("not a Standard MIDI File"),
               "and the strip names the file it could not read beside the clip it is still playing: "
               + statusLabel->getText());
        check (! statusLabel->getText().containsIgnoreCase ("Playing " + emptyClip.getFileName()),
               "without claiming to be playing the file it refused");

        check (emptyClip.existsAsFile() && emptyClip.getSize() == 0,
               "picking it wrote nothing and truncated nothing: the file is still 0 bytes");
        check (sha (clip) == clipHash && childNames (sandbox) == sandboxBeforePick,
               "and the real source and the sandbox are exactly as they were");

        panel->chooseRow (rowWithPath (panel, clip.getFullPathName()));
    }

    //==========================================================================
    // The drag's payload, without an OLE drag
    {
        juce::StringArray files;
        bool canMoveFiles = true;

        const juce::DragAndDropTarget::SourceDetails details {
            juce::var (clip.getFullPathName()), listBox, juce::Point<int>() };

        const bool wouldDrag = panel->shouldDropFilesWhenDraggedExternally (details, files,
                                                                          canMoveFiles);

        check (wouldDrag && files.size() == 1 && files[0] == clip.getFullPathName(),
               "a drag out of the browser carries the original library path, not a copy");
        check (! canMoveFiles,
               "and asks for a copy: a target that wants a move is told no, which is the rule that "
               "protects the source .mid");

        juce::StringArray others;
        bool otherCanMove = true;

        const juce::DragAndDropTarget::SourceDetails notListed {
            juce::var (sandbox.getChildFile ("keep me.mid").getFullPathName()), listBox,
            juce::Point<int>() };

        check (! panel->shouldDropFilesWhenDraggedExternally (notListed, others, otherCanMove),
               "a path this browser never listed is not draggable, so a drag is not a way to hand "
               "a host an arbitrary file");
    }

    //==========================================================================
    // "Copy path": the button, the clipboard, and what comes back out of it
    {
        const auto clipPath = clip.getFullPathName();

        // Read back through the same API the panel writes with. The assertion is about the
        // round trip, not about the call returning: JUCE's clipboard is a Win32 OpenClipboard /
        // SetClipboardData with a null owner, which needs no window and no message loop, so what
        // could go wrong here -- a wrong string, an empty clipboard, an early return -- shows up in
        // the text that comes back.
        check (click (*copyPathButton), "the Copy path button carries a click handler");
        check (juce::SystemClipboard::getTextFromClipboard() == clipPath,
               "and the clip's own path is what the clipboard now holds: "
               + juce::SystemClipboard::getTextFromClipboard());
        check (statusLabel->getText().containsIgnoreCase ("clipboard"),
               "and the strip says the path went somewhere: " + noteLine (statusLabel->getText()));
    }

    //==========================================================================
    // "Save clip as...": the byte copy, the one new file, and the refusals
    const auto sentinel = sandbox.getChildFile ("keep me.mid");
    sentinel.replaceWithText ("this is not a midi file");
    const auto sentinelHash = sha (sentinel);

    const auto beforeSave = childNames (sandbox);

    const auto exported = sandbox.getChildFile ("exported clip.mid");
    panel->saveClipCopyTo (exported, false);

    check (exported.existsAsFile(), "Save clip as creates the file it was pointed at");
    check (sha (exported) == clipHash,
           "and the copy's SHA-256 equals the source's: " + sha (exported).substring (0, 16) + "...");
    check (sha (clip) == clipHash, "the source .mid is byte-identical to what it was before the save");

    {
        const auto added = addedNames (beforeSave, childNames (sandbox));

        std::printf ("info  files the save added: %s\n", added.joinIntoString (", ").toRawUTF8());
        check (added.size() == 1 && added[0] == "exported clip.mid",
               "the save writes exactly one new file and changes no other");
    }

    // The strip's claim, read as one line and as the success sentence specifically. This used to be
    // contains ("byte-identical") over the whole block, which the refusal sentence also satisfies --
    // "Not saved: the file at X is not byte-identical to the clip" -- so it could not fail.
    const auto savedSentence = noteLine (statusLabel->getText());

    check (savedSentence.startsWith ("Saved a byte-identical copy at " + exported.getFullPathName()),
           "and the strip reports what landed, in the success sentence, in full: " + savedSentence);
    check (! savedSentence.startsWithIgnoreCase ("Not saved"),
           "and it is not a refusal that happens to use the same words: " + savedSentence);

    //==========================================================================
    // The chooser's contract: which prompt gates a replace, and what the callback does after it
    {
        check ((VaultEditor::saveChooserFlags() & juce::FileBrowserComponent::warnAboutOverwriting)
                 != 0,
               "the save chooser asks the operating system to warn about a replace, which is the "
               "only reason the callback below may replace without asking again");

        // A cancelled chooser: an empty path back, and the panel must write nothing and say nothing.
        const auto filesBeforeCancel = childNames (sandbox);
        const auto noteBeforeCancel  = statusLabel->getText();

        panel->handleChosenTarget ({});

        check (childNames (sandbox) == filesBeforeCancel,
               "a cancelled chooser creates, replaces and deletes nothing");
        check (statusLabel->getText() == noteBeforeCancel,
               "and does not even leave a sentence behind, because nothing was asked for");

        // A chosen target that already exists: this is the state the review's critical finding was
        // about. The old code asked a second question with an AlertWindow of its own, and non-native
        // JUCE numbers that box's first button 1 and its second 0 with Escape on the second
        // (juce_LookAndFeel_V2.cpp, createAlertWindow), so "chosen == 0" was Cancel: the replace ran
        // on a cancel and did nothing on a replace. Now the gate is the chooser's, and the callback
        // writes -- which is only safe while the check above holds.
        const auto olderDraft = sandbox.getChildFile ("older draft.mid");
        olderDraft.replaceWithText ("a clip the user is about to overwrite on purpose");
        const auto olderHash = sha (olderDraft);

        const auto filesBeforeReplace = childNames (sandbox);
        panel->handleChosenTarget (olderDraft);

        check (sha (olderDraft) == clipHash && olderDraft.existsAsFile(),
               "a target the user confirmed at the operating system's prompt is replaced, byte for "
               "byte -- the click that says yes is the one that writes");
        check (noteLine (statusLabel->getText()).startsWith ("Saved a byte-identical copy at "),
               "and the replace reports itself as a save, not as a refusal: "
               + noteLine (statusLabel->getText()));
        check (addedNames (filesBeforeReplace, childNames (sandbox)).isEmpty(),
               "and it replaced in place: no second file appeared");

        // The one path the panel still refuses by name, before any bytes are read: asking the user
        // to replace the clip's own source and then saying no would be a worse joke than a plain no.
        const auto sourceHashBefore = sha (clip);
        panel->handleChosenTarget (clip);

        check (sha (clip) == sourceHashBefore && sha (clip) == clipHash,
               "and choosing the file that is playing is still refused after the chooser's prompt");
        check (statusLabel->getText().containsIgnoreCase ("never written"),
               "in the words that say why: " + noteLine (statusLabel->getText()));
    }

    //==========================================================================
    // The 0-byte source: the one clip that cannot be copied, and the file that must survive it
    {
        const auto innocent = sandbox.getChildFile ("do not delete me.mid");
        innocent.replaceWithText ("bytes that an attempt to copy an empty clip must not be able to remove");
        const auto innocentHash = sha (innocent);

        // overwriteExisting = true, the shape that reaches the dangerous call: the user has
        // confirmed the replace at the prompt, so the panel asks nothing and hands the target to
        // copyClipVerbatim told to overwrite. Without the refusal, File::replaceWithData with a
        // zero length is deleteFile() (juce_File.cpp:777) and the file the user just named is gone,
        // with a hash-mismatch sentence as the only evidence anything happened.
        const auto attempt = vault::copyClipVerbatim (emptyClip, innocent, true);

        check (attempt.outcome == vault::ClipCopyOutcome::sourceEmpty,
               "a 0-byte source is refused on its own outcome, before anything is read or written");
        check (innocent.existsAsFile() && sha (innocent) == innocentHash,
               "and the target is still there with the bytes it had, which is the whole finding");
        check (attempt.message.containsIgnoreCase ("nothing was written")
                 && attempt.message.containsIgnoreCase ("left alone"),
               "and the sentence says both halves of that: " + attempt.message);
        check (attempt.bytes == 0 && attempt.sourceHash.isEmpty() && attempt.writtenHash.isEmpty(),
               "while claiming no digest and no byte count, so nothing in the result reads as a copy");
        check (emptyClip.existsAsFile() && emptyClip.getSize() == 0,
               "and the refusal did not touch the empty source either");

        // Disclosed, so this check is not read as more than it is: the panel's own save cannot be
        // walked into this branch, because a 0-byte file never becomes the playing clip -- the pick
        // block above measured that loadFile() refuses it and leaves the previous clip alone. What
        // is reachable from a click is the file's bytes having emptied after the load, which is a
        // copyClipVerbatim call with the live source, and the live source is what the five checks
        // above pass by hand. The strip's mapping of a refusal is proven by the same-path refusal
        // below, which goes through saveClipCopyTo.
    }

    //==========================================================================
    // The re-hash: the last defence, held to making the difference between two outcomes
    {
        const auto landed = sandbox.getChildFile ("short read.mid");
        const auto oneByteShort = static_cast<size_t> (clip.getSize()) - 1;

        // The write is fine here -- the file that lands is the clip. What is short is the read that
        // checks it, which is the state the reviewer's finding describes (File::replaceWithData
        // discards appendData's return and overwriteTargetFileWithTemporary retries the rename five
        // times) and the one a suite cannot ask the file system to produce on demand. So the read
        // back is capped, and what is proven is that the comparison, not the return code, decides
        // whether this build is allowed to say "Saved".
        const auto shortRead = vault::copyClipVerbatim (clip, landed, false, oneByteShort);

        check (shortRead.outcome == vault::ClipCopyOutcome::bytesDiffer,
               "a read-back one byte short of the source is a refusal, not a save: the re-hash "
               "decides the outcome");
        check (shortRead.message.containsIgnoreCase ("not byte-identical")
                 && shortRead.writtenHash.isNotEmpty() && shortRead.sourceHash.isNotEmpty()
                 && shortRead.writtenHash != shortRead.sourceHash,
               "and the sentence names both digests it compared: " + shortRead.message);
        check (sha (landed) == clipHash,
               "the refusal is about the claim, not about a broken file: what actually landed is "
               "the clip");

        // The trap this whole block exists to close, pinned so it cannot come back quietly: the
        // refusal sentence contains the success sentence's own word. The strip check above used to
        // be contains ("byte-identical") over the whole block, and a strip whose save had failed
        // with this message satisfied it -- which is how a green suite came to be reporting an
        // export check that could not fail.
        check (shortRead.message.containsIgnoreCase ("byte-identical"),
               "and the refusal sentence uses the success sentence's own word, which is why the "
               "strip check above names a prefix of one line instead of searching the block for it");

        const auto whole = vault::copyClipVerbatim (clip, landed, true);

        check (whole.outcome == vault::ClipCopyOutcome::wrote && sha (landed) == clipHash,
               "and the same source to the same target, read back in full as production always "
               "does, is the copy it says it is");
    }

    panel->saveClipCopyTo (clip, true);

    check (sha (clip) == clipHash,
           "the panel refuses to write the file it is playing, even when told to overwrite");
    check (statusLabel->getText().contains ("never written"),
           "and says why: a source .mid is never written");

    panel->saveClipCopyTo (sentinel, false);

    check (sha (sentinel) == sentinelHash,
           "an existing file is left alone when no one confirmed replacing it");

    panel->saveClipCopyTo (sentinel, true);

    check (sha (sentinel) == clipHash,
           "and is replaced, byte for byte, once a human has");

    //==========================================================================
    // The note's lifetime: three clicks change what its sentence would be about
    {
        const auto savedAbout = noteLine (statusLabel->getText());

        check (savedAbout.startsWith ("Saved a byte-identical copy at " + sentinel.getFullPathName()),
               "the last save's sentence is on the strip before the clicks that should retire it: "
               + savedAbout);

        // Rescan is a query. The rows are re-read from the index, and a note about a file this
        // build wrote two clicks ago must not survive to be read as the newest thing that happened.
        click (*rescanButton);

        check (! statusLabel->getText().containsIgnoreCase ("Saved a byte-identical copy"),
               "a query retires the note with the rows it re-read: "
               + noteLine (statusLabel->getText()));

        panel->saveClipCopyTo (exported, true);

        check (noteLine (statusLabel->getText()).startsWith ("Saved a byte-identical copy at "),
               "and a save puts it back, so the next click is tested against a live note");

        // Choosing a row is the click that makes the note a lie if it survives: the sentence names
        // a copy made of the clip that *was* playing.
        panel->chooseRow (rowWithPath (panel, clip.getFullPathName()));

        check (! statusLabel->getText().containsIgnoreCase ("Saved a byte-identical copy"),
               "and choosing a row retires the note before naming the clip that is playing now: "
               + noteLine (statusLabel->getText()));

        // The keystroke path is the same code as Rescan, and it is the one a producer uses while
        // hunting for the next clip, so it is checked as its own click.
        panel->saveClipCopyTo (exported, true);
        filterBox->setText ("Piano");
        pumpMessages();

        check (! statusLabel->getText().containsIgnoreCase ("Saved a byte-identical copy"),
               "typing in the filter retires it too, because the filter is a query like any other");

        filterBox->setText ("");
        pumpMessages();
    }

    //==========================================================================
    // A host-driven restore that cannot find its file
    juce::MemoryBlock savedBlob;
    processor.getStateInformation (savedBlob);

    std::unique_ptr<juce::XmlElement> savedXml (
        juce::AudioProcessor::getXmlFromBinary (savedBlob.getData(),
                                                static_cast<int> (savedBlob.getSize())));

    check (savedXml != nullptr, "the processor saves a readable state blob");

    if (savedXml != nullptr)
    {
        const auto absentPath = sandbox.getChildFile ("moved away.mid").getFullPathName();

        auto movedOn = *savedXml;
        movedOn.setAttribute ("sourceFile", absentPath);

        juce::MemoryBlock movedBlob;
        juce::AudioProcessor::copyXmlToBinary (movedOn, movedBlob);

        processor.setStateInformation (movedBlob.getData(), static_cast<int> (movedBlob.getSize()));
        panel->refreshStatus();

        const auto afterRestore = processor.status();
        const auto sentence     = statusLabel->getText();

        check (afterRestore.restore == VaultMIDIProcessor::ClipStatus::RestoreCheck::missing,
               "a project whose file is gone reports the file as missing");
        check (! afterRestore.loaded, "and leaves nothing playing under that claim");
        check (sentence.contains (absentPath),
               "the strip names the file the project wanted: " + sentence);
        check (sentence.contains ("not there"),
               "and says it is not there, which is the sentence that lets a moved drive be fixed "
               "instead of the clip re-picked");
        check (! sentence.containsIgnoreCase ("differs"),
               "without promising a verdict no digest can support");

        // The panel holds no reader between clicks, so there is nothing for a restore to
        // invalidate: the connection is a path and a name, and the next query reopens it.
        check (click (*rescanButton) && static_cast<int> (panel->rows().size()) == 4,
               "the browser still works after a host-driven restore, because no handle was held");
        check (statusLabel->getText().contains (libraryFolder.getFullPathName()),
               "and still names the index it is pointed at");
    }

    //==========================================================================
    // Disconnect, then unload: two different "nothing" states

    // A host can unload the clip from under a panel whose Copy path and Save clip as buttons were
    // enabled at the last refresh, so the two no-clip branches are reachable without a click that
    // the button states would have allowed. Driving them through onClick is the point: the handler
    // is what has to be safe, and the disabled state is only the panel's opinion about it.
    check (click (*copyPathButton), "Copy path still carries a handler with no clip loaded");
    check (statusLabel->getText().containsIgnoreCase ("Nothing to copy"),
           "and says there is nothing to copy rather than putting an empty string on the clipboard: "
           + noteLine (statusLabel->getText()));

    const auto filesBeforeRefusals = childNames (sandbox);

    check (click (*saveAsButton), "Save clip as still carries a handler with no clip loaded");
    check (statusLabel->getText().containsIgnoreCase ("Nothing to save"),
           "and refuses before the chooser is built, so no save dialog is standing on the user's "
           "screen over a clip that is not there: " + noteLine (statusLabel->getText()));
    check (childNames (sandbox) == filesBeforeRefusals,
           "and neither refusal wrote a file either");

    check (statusLabel->getText().containsIgnoreCase ("Nothing to save"),
           "the refusal is on the strip going into the last click of the session");

    check (click (*disconnectButton), "Disconnect carries a click handler");

    check (! statusLabel->getText().containsIgnoreCase ("Nothing to save")
             && ! statusLabel->getText().containsIgnoreCase ("Nothing to copy"),
           "and Disconnect retires the note with the connection it belongs to: "
           + noteLine (statusLabel->getText()));

    check (panel->rows().empty() && panel->connectedIndex().isEmpty(),
           "Disconnect empties the browser and forgets the index");
    check (statusLabel->getText().contains ("not connected"),
           "and the strip returns to not connected");
    check (statusLabel->getText().contains ("This project wants"),
           "while still naming the file the project asked for, which is the project's claim, not "
           "the index's");

    processor.unload();
    panel->refreshStatus();

    check (statusLabel->getText().contains ("No clip loaded"),
           "unload() leaves the panel saying there is no clip at all");

    //==========================================================================
    // Two index states a producer meets, the words for each, and what one failed read costs
    {
        const auto emptyRoot   = sandbox.getChildFile ("no-index");
        const auto badRoot     = sandbox.getChildFile ("not-an-index");
        const auto partialRoot = sandbox.getChildFile ("not-a-vault-index");
        const auto quietRoot   = sandbox.getChildFile ("quiet");

        emptyRoot.createDirectory();
        badRoot.createDirectory();
        partialRoot.createDirectory();
        quietRoot.createDirectory();

        const auto localAppDataBefore = environment ("LOCALAPPDATA");
        const auto programDataBefore  = environment ("PROGRAMDATA");

        // All four roots have to hold no index at once, or the second one wins and this is the
        // "first of N indexes found" branch instead. LOCALAPPDATA and PROGRAMDATA are what the
        // locator reads (VaultIndexLocator.cpp), and they have to be folders rather than empty
        // strings: an unset variable falls back to the real known folder, which on this machine
        // holds the user's index.
        setEnvironment ("SKEER_MIDIVAULT_DATA", emptyRoot.getFullPathName());
        setEnvironment ("LOCALAPPDATA", quietRoot.getFullPathName());
        setEnvironment ("PROGRAMDATA",  quietRoot.getFullPathName());

        check (click (*connectButton), "Connect runs the search again with no index anywhere");

        const auto noneText = statusLabel->getText();
        info ("no-index strip: " + noneText);

        check (noneText.containsIgnoreCase ("no index found. Looked for midivault.sqlite3 in"),
               "the strip says no index was found and names the file it looked for");
        check (noneText.contains (emptyRoot.getFullPathName())
                 && noneText.contains (quietRoot.getFullPathName()),
               "and names the folders it searched, which is the difference between \"there is no "
               "index\" and \"the app writes somewhere this build does not know about\"");
        check (! noneText.containsIgnoreCase ("not read this time"),
               "without reporting a read that never happened");
        check (panel->connectedIndex().isEmpty() && panel->rows().empty(),
               "with nothing found there is no connection and no rows");
        check (connectButton->isEnabled() && ! rescanButton->isEnabled()
                 && ! disconnectButton->isEnabled(),
               "and the only offer left is Connect again, because there is nothing to rescan or "
               "disconnect from");

        // Now two files with the index's name that are not an index, because they are two different
        // problems with two different pieces of advice. The old code answered both of them the same
        // way: by forgetting the connection, so a filter keystroke that landed while the app held
        // the file open, or while a drive had not spun up, threw the user back to "not connected"
        // and made them press Connect again to find the same path.
        const auto fakeIndex = badRoot.getChildFile ("midivault.sqlite3");
        fakeIndex.replaceWithText ("this is a text file wearing a database's name");

        setEnvironment ("SKEER_MIDIVAULT_DATA", badRoot.getFullPathName());

        check (click (*connectButton), "Connect onto a text file that is named like an index");

        const auto badText = statusLabel->getText();
        info ("not-a-database strip: " + badText);

        check (badText.containsIgnoreCase ("file is not a database"),
               "the reader's refusal reaches the strip in SQLite's own words");
        check (badText.containsIgnoreCase ("not read this time"),
               "and the panel adds the sentence that says what it means: this read did not come off");
        check (! badText.containsIgnoreCase ("not connected"),
               "and does not also make the different claim that there is no connection: " + badText);
        check (panel->connectedIndex() == fakeIndex.getFullPathName(),
               "while the index the user clicked Connect onto stays the index it is pointed at: "
               + panel->connectedIndex());
        check (panel->rows().empty() && ! badText.containsIgnoreCase ("usable files"),
               "with no rows and no count line, so nothing stale is offered as what is there now");
        check (! connectButton->isEnabled() && rescanButton->isEnabled()
                 && disconnectButton->isEnabled(),
               "and the buttons are the retry and the explicit end, not a second Connect");

        // Disconnect is what makes that promise real: forgetting the connection is a click the user
        // takes, never something a failed read does for them -- and it is the only route back to a
        // Connect that is enabled, which is what anyone changing roots actually has to do.
        check (click (*disconnectButton), "Disconnect is the explicit end, and the only route back to Connect");

        check (panel->connectedIndex().isEmpty() && connectButton->isEnabled()
                 && ! rescanButton->isEnabled() && ! disconnectButton->isEnabled(),
               "it forgets the path, the error and the button states together");

        // The other unreadable file: a real database with nothing vault-shaped in it. This is the
        // sentence that means "you pointed the plug-in at the wrong folder", and it is only
        // reachable once SQLite accepts the file as a database at all.
        const auto wrongBase = partialRoot.getChildFile ("midivault.sqlite3");

        check (makeDatabase (wrongBase.getFullPathName(),
                             "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
                             "CREATE TABLE somethingelse (id INTEGER PRIMARY KEY);")
                 && wrongBase.existsAsFile(),
               "a real SQLite database with neither files nor tracks is written in a third folder");

        setEnvironment ("SKEER_MIDIVAULT_DATA", partialRoot.getFullPathName());

        check (click (*connectButton), "Connect onto a database that is not a vault index");

        const auto wrongText = statusLabel->getText();
        info ("not-a-vault-index strip: " + wrongText);

        check (wrongText.containsIgnoreCase ("not a SKEER MIDI VAULT index")
                 && wrongText.containsIgnoreCase ("no files or tracks table"),
               "the strip says so in the reader's words, which name the tables it looked for");
        check (wrongText.containsIgnoreCase ("not read this time")
                 && panel->connectedIndex() == wrongBase.getFullPathName(),
               "and the connection still stands, in the same state as the other unreadable file");
        check (panel->rows().empty() && ! connectButton->isEnabled()
                 && rescanButton->isEnabled() && disconnectButton->isEnabled(),
               "with the same rows-and-buttons contract, so a user gets one behaviour for both");

        // The retry, with nothing re-pointed and no button touched but Rescan: the file becomes
        // what it was pretending to be, which is the shape of a transient failure.
        {
            wrongBase.deleteFile();

            FixtureWriter writer;

            if (! writer.open (wrongBase))
                return 1;

            check (writer.add (clip.getFullPathName(), clip.getFileName(), "Hat", 140.0, 16.0,
                               32, false, clipHash),
                   "a real index is written at the same path in the same folder, with one row");
        }

        check (click (*rescanButton), "Rescan is the retry the panel kept offering");

        const auto retryText = statusLabel->getText();

        check (static_cast<int> (panel->rows().size()) == 1,
               "and the connection that survived the failure reads the same path once the path is "
               "an index -- no Disconnect, no second Connect");
        check (retryText.containsIgnoreCase ("usable files")
                 && ! retryText.containsIgnoreCase ("not read this time")
                 && ! retryText.containsIgnoreCase ("not a SKEER MIDI VAULT index"),
               "with the refusal replaced by counts rather than merely older than them: " + retryText);
        check (panel->connectedIndex() == wrongBase.getFullPathName(),
               "still the same index path it was pointed at before the failure, and said so after");

        setEnvironment ("SKEER_MIDIVAULT_DATA", libraryFolder.getFullPathName());
        setEnvironment ("LOCALAPPDATA", localAppDataBefore);
        setEnvironment ("PROGRAMDATA",  programDataBefore);
    }

    //==========================================================================
    // The verdict wording the state model allows, checked without a host to produce each one
    {
        using Restore = VaultMIDIProcessor::ClipStatus::RestoreCheck;

        VaultMIDIProcessor::ClipStatus clipStatus;
        clipStatus.file = clipStatus.savedFile = "D:/Sets/a.mid";

        clipStatus.restore = Restore::differs;
        const auto differs = VaultEditor::describeClip (clipStatus);

        check (differs.contains ("not the ones this project was saved with"),
               "a recorded digest that does not match is called differs, in words");

        clipStatus.restore = Restore::matches;
        check (VaultEditor::describeClip (clipStatus).contains ("match the digest"),
               "a recorded digest that does match says so");

        clipStatus.restore = Restore::unreadable;
        clipStatus.error = "not a Standard MIDI File";
        check (VaultEditor::describeClip (clipStatus).contains ("will not open as MIDI"),
               "a file that is there but unreadable is a different sentence from a missing one");
    }

    {
        // The settled contract from the review-fix lane: a failed restore keeps the project's path
        // and drops its digest. `differs` is not available in that state, and the strip must not
        // promise it.
        VaultMIDIProcessor::ClipStatus dropped;
        dropped.savedFile = "E:/Sets/2.mid";
        dropped.restore   = VaultMIDIProcessor::ClipStatus::RestoreCheck::nothingSaved;

        const auto sentence = VaultEditor::describeClip (dropped);

        check (sentence.contains ("E:/Sets/2.mid") && ! sentence.containsIgnoreCase ("differs")
                 && ! sentence.containsIgnoreCase ("match"),
               "a project with no recorded digest is never given a matching verdict: " + sentence);
        check (sentence.contains ("nothing was loaded from it"),
               "and the strip says plainly that nothing came of it");
    }

    //==========================================================================
    // The session's bill: the library is exactly as it was, plus SQLite's two sidecars
    {
        const auto added = addedNames (folderBeforeOpen, childNames (libraryFolder));

        std::printf ("info  files the whole session added to the library folder: %s\n",
                     added.joinIntoString (", ").toRawUTF8());
        check (onlyTheWalPair (added) && added.size() == 2,
               "the whole session leaves the index folder holding only the -wal/-shm pair");
    }

    check (sha (indexFile) == indexHash, "the index file is byte-identical to what it was at the start");
    check (sha (clip) == clipHash, "and the source .mid was never written by anything this suite did");

    editor.reset();

    std::printf ("\n%d checks, %d failed\n", checks, failures);
    return failures > 0 ? 1 : 0;
}

#include "VaultEditor.h"

#include "VaultClipExport.h"
#include "VaultIndexLocator.h"

namespace
{

// Built per use rather than at namespace scope: a juce::Font is cheap, and a static one would run
// before anything has initialised the GUI layer.
juce::Font rowFont()    { return juce::Font (juce::FontOptions (14.0f)); }
juce::Font detailFont() { return juce::Font (juce::FontOptions (11.5f)); }
juce::Font labelFont()  { return juce::Font (juce::FontOptions (12.0f)); }

} // namespace

//==============================================================================
VaultEditor::VaultEditor (VaultMIDIProcessor& processorToUse)
    : AudioProcessorEditor (&processorToUse),
      processor (processorToUse)
{
    setOpaque (true);

    addAndMakeVisible (filterBox);
    filterBox.setComponentID ("vaultFilter");
    filterBox.setTextToShowWhenEmpty ("Filter by name or folder", juce::Colours::grey);
    filterBox.setFont (rowFont());
    filterBox.onTextChange = [this] { requery(); };

    for (auto* button : { &connectButton, &rescanButton, &disconnectButton, &copyPathButton,
                          &saveAsButton })
        addAndMakeVisible (*button);

    connectButton.setComponentID ("vaultConnect");
    rescanButton.setComponentID ("vaultRescan");
    disconnectButton.setComponentID ("vaultDisconnect");
    copyPathButton.setComponentID ("vaultCopyPath");
    saveAsButton.setComponentID ("vaultSaveAs");

    connectButton.onClick    = [this] { connectToIndex(); };
    rescanButton.onClick     = [this] { requery(); };
    disconnectButton.onClick = [this] { disconnectFromIndex(); };
    copyPathButton.onClick   = [this] { copyPathToClipboard(); };
    saveAsButton.onClick     = [this] { saveClipAs(); };

    addAndMakeVisible (list);
    list.setComponentID ("vaultList");
    list.setModel (this);
    list.setRowHeight (36);
    list.setMultipleSelectionEnabled (false);
    list.setColour (juce::ListBox::backgroundColourId, juce::Colours::black.withAlpha (0.2f));

    // The three exported parameters, permanently visible and never moved except by the user or the
    // host: the attachments are one-way mirrors onto the same parameters the audio thread reads, so
    // there is no second copy of a value here that could drift.
    for (auto* label : { &followTempoLabel, &transposeLabel, &loopLabel })
    {
        addAndMakeVisible (*label);
        label->setFont (labelFont());
        label->setColour (juce::Label::textColourId, juce::Colours::white.withAlpha (0.8f));
    }

    addAndMakeVisible (followTempoBox);
    followTempoBox.setComponentID ("vaultFollowTempo");
    followTempoBox.addItemList ({ "Off", "On" }, 1);

    addAndMakeVisible (loopBox);
    loopBox.setComponentID ("vaultLoop");
    loopBox.addItemList ({ "Once", "Loop" }, 1);

    addAndMakeVisible (transposeSlider);
    transposeSlider.setComponentID ("vaultTranspose");
    transposeSlider.setSliderStyle (juce::Slider::LinearHorizontal);
    transposeSlider.setTextBoxStyle (juce::Slider::TextBoxRight, false, 56, 22);
    transposeSlider.setRange (-24.0, 24.0, 1.0);

    followTempoAttachment = std::make_unique<juce::AudioProcessorValueTreeState::ComboBoxAttachment> (
        processor.valueTreeState, VaultMIDIProcessor::followTempoId, followTempoBox);
    transposeAttachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (
        processor.valueTreeState, VaultMIDIProcessor::transposeId, transposeSlider);
    loopAttachment = std::make_unique<juce::AudioProcessorValueTreeState::ComboBoxAttachment> (
        processor.valueTreeState, VaultMIDIProcessor::loopId, loopBox);

    addAndMakeVisible (statusText);
    statusText.setComponentID ("vaultStatus");
    statusText.setFont (juce::Font (juce::FontOptions (12.5f)));
    statusText.setJustificationType (juce::Justification::topLeft);
    statusText.setMinimumHorizontalScale (1.0f);
    statusText.setColour (juce::Label::textColourId, juce::Colours::white.withAlpha (0.9f));

    // Four refreshes a second: the audio thread's status is the only part of this panel that moves
    // without a click, and reading it is one lock and a handful of strings.
    startTimerHz (4);

    setResizable (true, false);
    setResizeLimits (480, 560, 1200, 1600);
    setSize (560, 640);

    refreshStatus();
}

VaultEditor::~VaultEditor()
{
    stopTimer();

    // The ListBox outlives this object's ListBoxModel base by an instant during destruction. Saying
    // so here is cheaper than relying on member ordering to be right by accident.
    list.setModel (nullptr);
}

//==============================================================================
juce::String VaultEditor::describeClip (const VaultMIDIProcessor::ClipStatus& clip)
{
    using Restore = VaultMIDIProcessor::ClipStatus::RestoreCheck;

    switch (clip.restore)
    {
        case Restore::missing:
            // The sentence only the panel can say, and the one that lets a producer fix a moved
            // drive instead of re-picking the clip from scratch. It names the path the *project*
            // asked for, which is `savedFile`, not whatever is or is not playing.
            return "This project wants " + clip.savedFile + ", and the file is not there";

        case Restore::unreadable:
            return "This project wants " + clip.savedFile
                   + ", and it is there but will not open as MIDI"
                   + (clip.error.isNotEmpty() ? " (" + clip.error + ")" : juce::String());

        case Restore::differs:
            return "Playing " + clip.file + " - the bytes are not the ones this project was saved with";

        case Restore::matches:
            return "Playing " + clip.file + " - the bytes match the digest this project was saved with";

        case Restore::nothingSaved:
        default:
            break;
    }

    if (clip.loaded)
        return "Playing " + clip.file + " - no saved digest was compared with these bytes"
               + (clip.error.isNotEmpty() ? " (" + clip.error + ")" : juce::String());

    if (clip.savedFile.isNotEmpty())
        // A project can name a file and carry no digest for it -- a pick, or a restore whose digest
        // an autosave dropped while the drive was away. `differs` is not available in that state and
        // this sentence does not promise it.
        return "This project names " + clip.savedFile + ", and nothing was loaded from it"
               + (clip.error.isNotEmpty() ? " (" + clip.error + ")" : juce::String());

    return "No clip loaded" + (clip.error.isNotEmpty() ? ": " + clip.error : juce::String());
}

void VaultEditor::refreshStatus()
{
    const auto clip = processor.status();

    juce::StringArray lines;

    if (indexFile.isEmpty())
        lines.add ("Index: not connected");
    else
    {
        lines.add ("Index: " + indexFile + " (" + indexOrigin + ")");

        if (usableFiles >= 0)
        {
            juce::String count;
            count << usableFiles << " usable files";

            if (static_cast<long long> (entries.size()) >= static_cast<long long> (rowLimit)
                 && usableFiles > static_cast<long long> (entries.size()))
                count << "; showing the first " << static_cast<int> (entries.size())
                      << " - narrow the filter to see the rest";
            else
                count << "; showing " << static_cast<int> (entries.size());

            lines.add (count);
        }
    }

    if (indexError.isNotEmpty())
        lines.add ("Index: " + indexError);

    lines.add (describeClip (clip));

    if (clip.loaded)
    {
        juce::String geometry ("Length: ");
        geometry << juce::String (clip.lengthBeats, 2) << " beats";

        if (clip.initialTempoBpm > 0.0)
            geometry << " at " << juce::String (clip.initialTempoBpm, 1) << " BPM";

        if (clip.tempoIsAssumed)
            geometry << " (assumed: the file never said)";

        if (! clip.hasBeatGrid)
            geometry << " - SMPTE timing, so Follow Host Tempo has no grid to follow";

        if (clip.waitingForTransport)
            geometry << " - waiting for the transport";

        lines.add (geometry);
    }

    if (exportNote.isNotEmpty())
        lines.add (exportNote);

    statusText.setText (lines.joinIntoString ("\n"), juce::dontSendNotification);

    connectButton.setEnabled (indexFile.isEmpty());
    rescanButton.setEnabled (indexFile.isNotEmpty());
    disconnectButton.setEnabled (indexFile.isNotEmpty());
    copyPathButton.setEnabled (clip.loaded);
    saveAsButton.setEnabled (clip.loaded);
}

//==============================================================================
void VaultEditor::connectToIndex()
{
    const auto roots = vault::IndexRoots::fromRuntime();
    const auto found = vault::findIndexes (roots);

    indexFile.clear();
    indexOrigin.clear();
    indexError.clear();
    entries.clear();
    usableFiles = -1;

    if (found.empty())
    {
        // Naming what was looked at is the difference between "there is no index" and "the app is
        // writing somewhere this build does not know about", and only one of those is the user's
        // problem to fix.
        juce::StringArray looked;

        for (const auto* root : { &roots.environment, &roots.user, &roots.machine, &roots.sideBySide })
            if (root->isNotEmpty())
                looked.add (*root);

        indexError = "no index found. Looked for " + vault::indexFileName() + " in: "
                   + looked.joinIntoString (", ");
        list.updateContent();
        refreshStatus();
        return;
    }

    // The first hit wins, in the locator's documented priority order, and the origin travels with
    // it so the strip can say which of the four places this library came from.
    indexFile   = juce::File (found.front().directory).getChildFile (vault::indexFileName()).getFullPathName();
    indexOrigin = found.front().origin;

    if (found.size() > 1)
        indexOrigin << ", first of " << static_cast<int> (found.size()) << " indexes found";

    requery();
}

void VaultEditor::disconnectFromIndex()
{
    indexFile.clear();
    indexOrigin.clear();
    indexError.clear();
    entries.clear();
    usableFiles = -1;
    exportNote.clear();

    // This is the one click that means "forget the connection", and it is the only place the path
    // goes away besides Connect itself. A failed read does not get here on its own: see requery().
    list.updateContent();
    refreshStatus();
}

void VaultEditor::requery()
{
    entries.clear();
    usableFiles = -1;
    indexError.clear();

    // A query is a new look at the library, so whatever the last save or copy reported is no longer
    // the newest thing the strip could say. The note is retired here, on choosing a row, and on
    // Disconnect -- the three clicks that change what the sentence would be about.
    exportNote.clear();

    if (indexFile.isNotEmpty())
    {
        // Every query happens here, on the message thread, in a reader that is opened and closed
        // inside this function. processBlock never asks the index anything, and nothing of the
        // user's library is held open between clicks -- so a host-driven setStateInformation has no
        // connection to invalidate, and no query of ours can be holding stateLock.
        vault::IndexReader reader;

        if (! reader.open (indexFile))
        {
            // One failed read is not a lost connection. An index can refuse this build for a second
            // at a time -- the app is between its commit and its close, the library is on a drive
            // that has not spun up, a scan holds the lock past our timeout -- and a panel that
            // answered that by forgetting which index the user asked for would make them go and
            // find it again to see the rows that come back on the next keystroke. So the path and
            // its origin stay, which is also what keeps Rescan and Disconnect meaningful: they are
            // the retry and the explicit end, and Disconnect is the only click that forgets.
            //
            // What does go is the rows. Showing yesterday's list over an index this build just
            // refused is the half-read the schema check exists to prevent, and the strip has to say
            // two different things in the right order: this is the index it is pointed at, and this
            // read did not come off.
            indexError = reader.errorMessage()
                       + " - the index was not read this time. The plug-in is still pointed at it; "
                         "press Rescan to try again, or Disconnect to forget it";
        }
        else
        {
            usableFiles = reader.countUsableFiles();
            entries     = reader.listFiles (rowLimit, filterBox.getText().trim());

            if (usableFiles < 0 && reader.errorMessage().isNotEmpty())
                indexError = reader.errorMessage();
        }
    }

    list.updateContent();
    refreshStatus();
}

//==============================================================================
void VaultEditor::chooseRow (int row)
{
    if (! juce::isPositiveAndBelow (row, static_cast<int> (entries.size())))
        return;

    // The note on the strip is about the clip that *was* playing, and a click changes that before
    // anything else does. Left standing, "Saved a byte-identical copy at ..." would sit under a
    // different file and read as a claim about this one.
    exportNote.clear();

    // One path to a playing clip: the processor's loadFile(), which publishes the path and the
    // three state keys under one lock. The panel writes none of them -- a second writer is exactly
    // the two-authority defect that class was fixed for.
    processor.loadFile (entries[static_cast<size_t> (row)].path);
    refreshStatus();
}

void VaultEditor::copyPathToClipboard()
{
    const auto clip = processor.status();

    if (clip.file.isEmpty())
    {
        setNote ("Nothing to copy: no clip is loaded");
        return;
    }

    // Neither leg of juce::SystemClipboard admits it failed: a write whose OpenClipboard is refused
    // is skipped by a void function, and a refused read comes back as an empty String
    // (juce_Windowing_windows.cpp:5694 and :5723). The clipboard is one desktop-wide resource with a
    // queue of viewers on it, so a refusal is ordinary traffic on a producer's machine rather than an
    // error this panel caused. Write, then believe the read rather than the call, and say which of
    // the two happened -- the strip is the only place a user can see whether the paste will work.
    auto copied = false;

    for (int attempt = 0; attempt < 4 && ! copied; ++attempt)
    {
        juce::SystemClipboard::copyTextToClipboard (clip.file);
        copied = (juce::SystemClipboard::getTextFromClipboard() == clip.file);

        if (! copied && attempt < 3)
            juce::Thread::sleep (15);  // a viewer's hold lasts milliseconds; the next attempt usually lands
    }

    setNote (copied ? "The clip's path is on the clipboard"
                    : "Not copied: the clipboard is busy, click Copy path again");
}

int VaultEditor::saveChooserFlags()
{
    // saveMode + canSelectFiles is the "one file, may be new" chooser. warnAboutOverwriting is the
    // part that carries a data-loss rule, and it is not decoration: on Windows it becomes
    // FOS_OVERWRITEPROMPT on the IFileSaveDialog, or OFN_OVERWRITEPROMPT on the legacy path
    // (juce_FileChooser_windows.cpp:199 and :611), and in the non-native chooser it is the flag
    // FileChooserDialogBox::okButtonPressed uses to put up its own confirm (juce_FileChooserDialogBox.cpp:196).
    // Either way, the dialog -- not this code -- is what asks, and the callback only ever sees a
    // target the user has already agreed to replace.
    return juce::FileBrowserComponent::saveMode
         | juce::FileBrowserComponent::canSelectFiles
         | juce::FileBrowserComponent::warnAboutOverwriting;
}

void VaultEditor::handleChosenTarget (const juce::File& target)
{
    if (target == juce::File())
        return;  // the chooser was cancelled; nothing was asked for and nothing is reported

    const auto clip = processor.status();

    if (clip.file.isEmpty())
    {
        setNote ("Nothing to save: no clip is loaded");
        return;
    }

    const juce::File source (clip.file);

    // Naming the protected file as soon as it comes back, rather than writing it and then saying no:
    // the OS has already asked "replace this file?" about the clip's own source, and to answer that
    // and be refused is a worse joke than a plain refusal. copyClipVerbatim checks this again,
    // against resolved paths and ignoring case -- this one only decides what the user is told.
    if (target.getFullPathName().equalsIgnoreCase (source.getFullPathName()))
    {
        setNote ("Not saved: that is the file the clip is playing from, and a source "
                 ".mid is never written. Choose another name");
        return;
    }

    // No second question here, deliberately: saveChooserFlags() asked the OS, and a confirm of our
    // own would be a second gate over a decision the user just made. That is the shape an
    // AlertWindow of our own kept getting wrong -- non-native JUCE numbers the first button 1 and
    // the second 0, with Escape on the second (juce_LookAndFeel_V2.cpp, createAlertWindow), so
    // "chosen == 0" was Cancel, and the box replaced on a cancel and did nothing on a replace.
    // If a confirm box is ever added back, that numbering has to be re-read from the source, not
    // assumed, and the check that drives it has to be added with it.
    //
    // overwriteExisting still reaches copyClipVerbatim: the targetExists refusal stays as the
    // backstop for any caller that came here without the chooser, and the source-empty and
    // same-path refusals are not things a prompt can be trusted to have handled.
    saveClipCopyTo (target, true);
}

void VaultEditor::saveClipAs()
{
    const auto clip = processor.status();

    if (clip.file.isEmpty())
    {
        setNote ("Nothing to save: no clip is loaded");
        return;
    }

    chooser = std::make_unique<juce::FileChooser> (
        "Save a copy of the clip",
        juce::File::getSpecialLocation (juce::File::userMusicDirectory).getChildFile (
            juce::File (clip.file).getFileName()),
        "*.mid");

    // The chooser answers later, and the host may close this window in between. A SafePointer is
    // what keeps a late answer from writing through a dead editor.
    juce::Component::SafePointer<VaultEditor> safeThis (this);

    chooser->launchAsync (saveChooserFlags(), [safeThis] (const juce::FileChooser& fc)
    {
        if (auto* editor = safeThis.getComponent())
            editor->handleChosenTarget (fc.getResult());
    });
}

void VaultEditor::saveClipCopyTo (const juce::File& target, bool overwriteExisting)
{
    const auto clip = processor.status();

    if (clip.file.isEmpty())
    {
        setNote ("Not saved: no clip is loaded");
        return;
    }

    const auto result = vault::copyClipVerbatim (juce::File (clip.file), target, overwriteExisting);

    if (result.outcome == vault::ClipCopyOutcome::wrote)
        setNote ("Saved a byte-identical copy at " + result.message);
    else
        setNote ("Not saved: " + result.message);
}

void VaultEditor::setNote (const juce::String& note)
{
    exportNote = note;
    refreshStatus();
}

//==============================================================================
int VaultEditor::getNumRows()
{
    return static_cast<int> (entries.size());
}

void VaultEditor::paintListBoxItem (int rowNumber, juce::Graphics& g, int width, int /*height*/,
                                    bool rowIsSelected)
{
    if (! juce::isPositiveAndBelow (rowNumber, static_cast<int> (entries.size())))
        return;

    const auto& entry = entries[static_cast<size_t> (rowNumber)];

    if (rowIsSelected)
        g.fillAll (juce::Colours::white.withAlpha (0.14f));

    g.setColour (juce::Colours::white.withAlpha (0.95f));
    g.setFont (rowFont());
    g.drawText ((entry.favorite ? "* " : "  ") + entry.filename, 8, 2, width - 16, 18,
                juce::Justification::centredLeft, true);

    juce::String detail;

    if (entry.instrument.isNotEmpty())
        detail << entry.instrument << "  ";

    if (entry.role.isNotEmpty())
        detail << entry.role << "  ";

    if (entry.tempoBpm > 0.0)
        detail << juce::String (entry.tempoBpm, 1) << " BPM  ";

    if (entry.durationBeats > 0.0)
        detail << juce::String (entry.durationBeats, 1) << " beats  ";

    detail << entry.noteCount << " notes";

    g.setColour (juce::Colours::white.withAlpha (0.6f));
    g.setFont (detailFont());
    g.drawText (detail, 8, 19, width - 16, 14, juce::Justification::centredLeft, true);
}

void VaultEditor::listBoxItemClicked (int row, const juce::MouseEvent&)
{
    chooseRow (row);
}

juce::var VaultEditor::getDragSourceDescription (const juce::SparseSet<int>& rowsToDescribe)
{
    if (rowsToDescribe.size() != 1)
        return {};

    const auto row = rowsToDescribe[0];

    if (! juce::isPositiveAndBelow (row, static_cast<int> (entries.size())))
        return {};

    // The row's own path is the drag's description; shouldDropFilesWhenDraggedExternally() turns it
    // into the file list once the pointer leaves the window.
    return entries[static_cast<size_t> (row)].path;
}

bool VaultEditor::shouldDropFilesWhenDraggedExternally (
    const juce::DragAndDropTarget::SourceDetails& details, juce::StringArray& files,
    bool& canMoveFiles)
{
    const juce::File dragged (details.description.toString());

    // Only a file this browser listed can leave it: a drag is an offer of this library's bytes, not
    // a way to hand a host an arbitrary path. And it is the original path, not a %TEMP% copy -- a
    // copy would break the digest tie to the index row and duplicate library files behind the
    // user's back.
    bool listed = false;

    for (const auto& entry : entries)
        listed = listed || entry.path.equalsIgnoreCase (dragged.getFullPathName());

    if (! listed || ! dragged.existsAsFile())
        return false;

    files.add (dragged.getFullPathName());

    // A drag out of the library is a copy. juce_DragAndDrop_windows.cpp:323-338 turns this into a
    // DROPEFFECT_COPY-only effect mask, so even a target that asks for a move is told no.
    canMoveFiles = false;
    return true;
}

//==============================================================================
void VaultEditor::timerCallback()
{
    refreshStatus();
}

//==============================================================================
void VaultEditor::paint (juce::Graphics& g)
{
    g.fillAll (juce::Colour (0xff202024));
}

void VaultEditor::resized()
{
    auto area = getLocalBounds().reduced (8);

    auto top = area.removeFromTop (26);
    static constexpr int buttonWidth = 90;

    disconnectButton.setBounds (top.removeFromRight (buttonWidth));
    top.removeFromRight (4);
    rescanButton.setBounds (top.removeFromRight (buttonWidth));
    top.removeFromRight (4);
    connectButton.setBounds (top.removeFromRight (buttonWidth));
    top.removeFromRight (6);
    filterBox.setBounds (top);

    area.removeFromTop (6);

    statusText.setBounds (area.removeFromBottom (92));
    area.removeFromBottom (6);

    auto exportRow = area.removeFromBottom (26);
    copyPathButton.setBounds (exportRow.removeFromLeft (110));
    exportRow.removeFromLeft (6);
    saveAsButton.setBounds (exportRow.removeFromLeft (130));

    area.removeFromBottom (8);

    auto paramRow = area.removeFromBottom (52);
    const auto columnWidth = paramRow.getWidth() / 3;

    auto tempoArea = paramRow.removeFromLeft (columnWidth).reduced (2, 0);
    followTempoLabel.setBounds (tempoArea.removeFromTop (18));
    followTempoBox.setBounds (tempoArea.removeFromTop (28).reduced (0, 1));

    auto transposeArea = paramRow.removeFromLeft (columnWidth).reduced (2, 0);
    transposeLabel.setBounds (transposeArea.removeFromTop (18));
    transposeSlider.setBounds (transposeArea.removeFromTop (28));

    auto loopArea = paramRow.reduced (2, 0);
    loopLabel.setBounds (loopArea.removeFromTop (18));
    loopBox.setBounds (loopArea.removeFromTop (28).reduced (0, 1));

    area.removeFromBottom (8);
    list.setBounds (area);
}

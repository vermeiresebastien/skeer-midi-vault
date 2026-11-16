#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_gui_basics/juce_gui_basics.h>

#include "VaultIndexReader.h"
#include "VaultMIDIProcessor.h"

#include <memory>
#include <vector>

// The plug-in's front door: an index browser that hands a clip to the host and says, in words,
// what it is playing and what the project asked for.
//
// Three rules shape this file, and they are the ones a reviewer should hold it to:
//
//   1. The index is read, never written, and only on the message thread. There is no reader member
//      at all: every query opens one, asks its question and closes it. That is a little more work
//      per keystroke and it buys two properties that are worth more -- no handle on the user's
//      library outlives the click that asked for it, so a host-driven setStateInformation cannot
//      leave this panel holding a connection into a folder that may have just changed underneath
//      it; and no query can be holding stateLock, because there is no lock here to hold.
//   2. A clip becomes the playing clip only through VaultMIDIProcessor::loadFile(). The panel never
//      writes sourceFile/sourceHash/stateVersion: those three keys are the processor's claim about
//      what is playing, and a second writer is how the two-authority defect in that class arose.
//   3. Nothing here is silent. Connecting is a button, the index root and its origin are printed,
//      and what the drag and the save do are two buttons a user can see.
//
// The panel shows no audio and has none: this processor declares no audio buses, so an audition
// would be a claim it cannot keep. The host that loaded the plug-in is where the clip is heard.
class VaultEditor final : public juce::AudioProcessorEditor,
                          public juce::DragAndDropContainer,
                          private juce::ListBoxModel,
                          private juce::Timer
{
public:
    explicit VaultEditor (VaultMIDIProcessor&);
    ~VaultEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

    /** The sentence the status strip prints about the clip.

        Static and public because the wording is a contract with the state model, and the sixth
        suite holds it to one without opening a window: `restore` decides which sentence, `file` is
        what is playing, `savedFile` is what the project wants, and `differs` is a verdict only a
        recorded digest can support -- a project whose digest was dropped by an autosave while its
        drive was away cannot be called `differs`, and this function never does. */
    static juce::String describeClip (const VaultMIDIProcessor::ClipStatus&);

    /** The rows on screen, exactly as the last query answered. Public because the panel's own
        status line counts them and a headless check holds the filter to them. */
    const std::vector<vault::LibraryEntry>& rows() const noexcept { return entries; }

    /** The index file the panel is pointed at; empty while not connected. */
    juce::String connectedIndex() const { return indexFile; }

    /** Rebuilds the status strip and the button states from the processor. The timer calls this;
        it is public so a headless check can ask for the same refresh without a message loop. */
    void refreshStatus();

    /** What a click on a row does. Called by listBoxItemClicked(); public so a check can drive the
        browser without synthesising a MouseEvent. Clears the note from the last save first: that
        note is about the row the user was on, and leaving it under a different clip would let the
        strip claim a copy that belongs to another file. */
    void chooseRow (int row);

    /** The half of "Save clip as..." that does the work, with no dialog in front of it: the file
        chooser's callback calls this, and so does the sixth suite. Refusals land in the status
        strip, in words, whichever caller asked. */
    void saveClipCopyTo (const juce::File& target, bool overwriteExisting);

    /** The post-chooser half of "Save clip as...": what happens to a path the chooser returned,
        including the empty path that means the user cancelled. Public and dialog-free because a
        headless check has no OS prompt to answer -- and it is the *only* half a check can answer,
        which is the reason it is a separate function rather than four more lines in a lambda.
        The two things it has to get right: a chosen file that already exists is replaced without a
        second question here, because saveChooserFlags() already made the OS ask, and the file the
        clip is playing from is refused before anything is written. */
    void handleChosenTarget (const juce::File& target);

    /** The flags this panel hands to FileChooser::launchAsync for "Save clip as...". A function and
        not a literal at the call site because one of these bits *is* the overwrite gate: with
        warnAboutOverwriting the chooser returns a target only after a human has agreed to replace
        whatever was there, and handleChosenTarget's "no second question" is safe on exactly that
        strength. The check that the gate is requested reads it here, where it is used. */
    static int saveChooserFlags();

    /** The outbound drag. The row drag starts in the ListBox; the container asks this what the drag
        carries when the pointer leaves the window, and the answer is the original library path with
        canMoveFiles left false -- juce_DragAndDrop_windows.cpp:323-338 turns that into DROPEFFECT_COPY
        only, so a target that asks for a move is told no rather than obeyed. Public because this is
        testable without an OLE drag; whether a hosted editor can start one Live accepts is not
        something this repo has measured. */
    bool shouldDropFilesWhenDraggedExternally (const juce::DragAndDropTarget::SourceDetails& details,
                                               juce::StringArray& files,
                                               bool& canMoveFiles) override;

    /** How many rows one query may return. A 48,000-row index copied into a ListBox is a frozen
        window, and the filter is right there: `listFiles` is capped, and when the cap bites the
        status strip says so instead of pretending the library ends. */
    static constexpr int rowLimit = 200;

private:
    //==============================================================================
    int getNumRows() override;
    void paintListBoxItem (int rowNumber, juce::Graphics&, int width, int height,
                           bool rowIsSelected) override;
    void listBoxItemClicked (int row, const juce::MouseEvent&) override;
    juce::var getDragSourceDescription (const juce::SparseSet<int>& rowsToDescribe) override;

    void connectToIndex();
    void disconnectFromIndex();
    void requery();
    void copyPathToClipboard();
    void saveClipAs();
    void timerCallback() override;

    void setNote (const juce::String& note);

    VaultMIDIProcessor& processor;

    juce::TextEditor filterBox;
    juce::ListBox list { "vault rows", nullptr };
    juce::TextButton connectButton { "Connect" }, rescanButton { "Rescan" },
                     disconnectButton { "Disconnect" }, copyPathButton { "Copy path" },
                     saveAsButton { "Save clip as..." };

    juce::Label followTempoLabel { {}, "Follow Host Tempo" };
    juce::Label transposeLabel   { {}, "Transpose" };
    juce::Label loopLabel        { {}, "Loop" };
    juce::ComboBox followTempoBox, loopBox;
    juce::Slider transposeSlider;

    std::unique_ptr<juce::AudioProcessorValueTreeState::ComboBoxAttachment> followTempoAttachment,
                                                                          loopAttachment;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment>   transposeAttachment;

    juce::Label statusText;
    std::unique_ptr<juce::FileChooser> chooser;

    // The connection is a file path and a name for where it came from, not an open handle: see the
    // note at the top of this file. Empty means not connected, which is the state a freshly
    // inserted plug-in and a restored project both start in -- a restored project re-opens its clip
    // file, not the index, and pretending otherwise would mean browsing a library the project never
    // named.
    juce::String indexFile, indexOrigin, indexError;

    long long usableFiles = -1;
    std::vector<vault::LibraryEntry> entries;

    juce::String exportNote;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (VaultEditor)
};

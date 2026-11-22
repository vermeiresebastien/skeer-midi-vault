cmake_minimum_required(VERSION 3.22)

project(SkeerMidiVaultPlugin VERSION 1.1.2 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

enable_testing()

# JUCE 8.0.8, the same tag pulsekit builds against. A local checkout can be supplied with
# -DFETCHCONTENT_SOURCE_DIR_JUCE=<path>, which is what the build script does on a machine
# whose network makes a 100 MB shallow clone the slowest part of the day.
include(FetchContent)
FetchContent_Declare(
    JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG 8.0.8
    GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(JUCE)

# One source list, shared by the plugin and by every test binary, so a file cannot be added
# to the plugin and quietly left out of the checks. The locator is split out because a test
# of discovery should not have to compile the audio graph.
set(VAULT_CORE_SOURCES
    Source/VaultIndexLocator.cpp
    Source/VaultIndexReader.cpp)

# The source-file reader needs juce_audio_basics for MidiFile, which the two index tests do not
# link, so it is kept out of VAULT_CORE_SOURCES rather than dragging a whole audio module into
# every console target.
set(VAULT_MIDI_SOURCES
    Source/VaultMidiSource.cpp)

# The clip clock is as independent of the plug-in wrapper as the reader is: it takes a parsed file
# and a description of a transport and produces events, so the behaviour of step 5 is testable
# without a host, which is the only way it can be tested at all.
set(VAULT_EMIT_SOURCES
    Source/VaultMidiEmitter.cpp)

# The front door: the panel and the byte-verbatim export. Both are GUI-side code, and both are
# needed by every target that compiles VaultMIDIProcessor.cpp, because createEditor() is part of
# that class's vtable -- a target that left the editor out would fail to link rather than run
# without a window.
set(VAULT_EDITOR_SOURCES
    Source/VaultEditor.cpp
    Source/VaultClipExport.cpp)

set(VAULT_PLUGIN_SOURCES
    ${VAULT_CORE_SOURCES}
    ${VAULT_MIDI_SOURCES}
    ${VAULT_EMIT_SOURCES}
    ${VAULT_EDITOR_SOURCES}
    Source/VaultMIDIProcessor.cpp)

set(VAULT_DEFINES
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0)

# ---------------------------------------------------------------------------
# SQLite, from the vendored amalgamation
#
# Its own target, compiled once, with its own flags: recommended JUCE warning flags belong to
# our sources, not to 9.5 MB of somebody else's C. SQLITE_OMIT_WAL is deliberately NOT set --
# the app's index is in WAL mode, and a reader built without WAL cannot open it while a -wal
# file exists, which is most of the time.
# ---------------------------------------------------------------------------
add_library(VaultSQLite STATIC external/sqlite/sqlite3.c)

target_include_directories(VaultSQLite PUBLIC external/sqlite)

target_compile_definitions(VaultSQLite PUBLIC
    SQLITE_THREADSAFE=1
    SQLITE_OMIT_LOAD_EXTENSION
    SQLITE_OMIT_DEPRECATED
    SQLITE_DEFAULT_MEMSTATUS=0)

if (MSVC)
    # The amalgamation is C, and MSVC's own analysis pass reports on it as if it were ours.
    target_compile_options(VaultSQLite PRIVATE /wd4267 /wd4244 /wd4100)
endif()

# ---------------------------------------------------------------------------
# The plug-in
# ---------------------------------------------------------------------------
juce_add_plugin(SkeerMidiVaultPlugin
    COMPANY_NAME "Skeer Audio"
    # The two codes below are the durable half of this file and the name above is not. Both appear in
    # the VST3 class ID: bytes 9-16 of every CID this bundle publishes are ASCII 'SkAuMvlt', read out
    # of the shipped moduleinfo.json, and every sibling product's CID is its own two codes the same
    # way. A host recalls a saved instance by that CID, so changing either code orphans every project
    # that already holds this plug-in. COMPANY_NAME reaches only the vendor display string, which is
    # free to change at the cost of one rescan -- PulseKit changed its vendor string and its code stayed.
    # SkAu is shared with SKULPT (Skpt), so it is the pair, not the manufacturer half, that is unique.
    PLUGIN_MANUFACTURER_CODE SkAu
    PLUGIN_CODE Mvlt
    # Derived from the target name, the default reads 'com.Skeer Audio.SkeerMidiVaultPlugin'
    # -- a space inside a reverse-DNS identifier, which JUCE warns about and macOS would not
    # accept. Spelling it out also keeps it stable if the product name is ever reworded.
    BUNDLE_ID com.skeeraudio.midivault
    # TRUE, decided 2026-11-22 for 1.1.2: this device hands the host a MIDI clip, and someone
    # hunting for a source of notes opens the Instruments drawer, not the reverb drawer. The class
    # ID is untouched by this -- it comes from the two codes above -- so a project saved against
    # the Fx-era device still resolves. What does move, measured in the 8.0.4 VST3 wrapper: with
    # IS_SYNTH set, JucePlugin_Vst3ComponentFlags becomes Vst::kSimpleModeSupported, which
    # advertises that a host may route in simple per-voice mode. The other branch IS_SYNTH selects
    # -- reporting every audio output bus as kMain -- is unreachable here, because BusesProperties()
    # in plugin/Source/VaultMIDIProcessor.cpp declares no audio buses at all.
    IS_SYNTH TRUE
    NEEDS_MIDI_INPUT TRUE
    NEEDS_MIDI_OUTPUT TRUE
    IS_MIDI_EFFECT TRUE
    # TRUE, deliberately: the panel has a filter box, and a text field that cannot receive
    # keystrokes is a defect. The cost is the other half of the same coin -- the host routes keys
    # to this window while it has focus, so a producer's next keystroke after clicking into the
    # filter goes to the search box rather than to a host shortcut. That is what every plug-in with
    # a search field does, and the host gets its keys back the moment focus leaves. Left FALSE, the
    # filter would be typeable only when the host chose to pass keys through, which is a per-host
    # lottery, and a search box that sometimes swallows typing is worse than one that takes focus.
    EDITOR_WANTS_KEYBOARD_FOCUS TRUE
    # The installer is the only thing that may place a bundle. Left TRUE, JUCE copies the
    # build straight into a scanned VST3 folder on every compile, which is exactly how a
    # second copy of one plugin comes to exist.
    COPY_PLUGIN_AFTER_BUILD FALSE
    FORMATS VST3
    PRODUCT_NAME "SKEER MIDI VAULT"
    # This line, not IS_SYNTH, is what files the device. Measured in the 8.0.4 tree this builds
    # against: _juce_get_vst3_category_string consults JUCE_IS_SYNTH only when the list names
    # neither Fx nor Instrument, and otherwise hoists whichever of those two it finds to the front
    # of the pipe-joined string. Flipping IS_SYNTH while leaving Fx here would therefore have kept
    # the device in the effects drawer -- the wrapper's own IS_SYNTH-derived category fallback never
    # fires under CMake, which always defines that macro from this list -- but it would not have been
    # a no-op, because the simple-mode class flag above is live whatever this list says. Instrument
    # and Synth together are what JUCE itself derives from IS_SYNTH, and they are spelled out so the
    # drawer is a decision in this file rather than a default inherited from another repo. Verified
    # after the build, not before it: the shipped moduleinfo.json must read Sub Categories
    # ["Instrument","Synth"], and packaging\build_installer.ps1 refuses to stage a bundle that
    # says otherwise.
    VST3_CATEGORIES Instrument Synth)

# What this switch buys, measured: with it at its default, a host loading this bundle was
# offered the plugin's own controls plus Bypass and 16 channels x 130 auto-published "MIDI CC
# ch|cc" controls -- 2080 parameters on top of a list the user can actually read. The emulation
# exists so a host can drive a plugin's MIDI *input* by automating parameters; this plugin reads
# notes, never remote-controlled CCs, and it produces CCs as output events, which need no
# parameter. So those 2080 controls would only ever be noise in a DAW's parameter list.
# Set on the plugin target, not in VAULT_DEFINES: the host test compiles no wrapper, and a
# switch that only means something to one binary should not appear in the other's flags.
target_compile_definitions(SkeerMidiVaultPlugin_VST3 PRIVATE
    JUCE_VST3_EMULATE_MIDI_CC_WITH_PARAMETERS=0)

target_sources(SkeerMidiVaultPlugin PRIVATE ${VAULT_PLUGIN_SOURCES})
target_include_directories(SkeerMidiVaultPlugin PRIVATE Source)
target_compile_definitions(SkeerMidiVaultPlugin PUBLIC ${VAULT_DEFINES})

target_link_libraries(SkeerMidiVaultPlugin
    PRIVATE
        juce::juce_audio_utils
        # VaultMidiSource hashes the bytes it reads, and juce::SHA256 lives in a module no other
        # JUCE target pulls in. Measured: without this the plugin compiles, the shared-code library
        # builds, and only the VST3 link reports three unresolved juce::SHA256 symbols -- which is
        # to say the defect shows up one step past the point where it is cheap to see.
        juce::juce_cryptography
        VaultSQLite
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_warning_flags)

# The VST3 SDK's module-info writer leaves trailing commas in moduleinfo.json, which is
# invalid JSON. JUCE forgives it; a strict host does not, and its answer is to leave the
# plugin out of the browser without saying so. Ported from pulsekit/cmake and
# skulpt/cmake, where the same build step has run for two other products.
add_custom_command(TARGET SkeerMidiVaultPlugin_VST3 POST_BUILD
    COMMAND ${CMAKE_COMMAND}
            "-DVC_FILE=$<TARGET_FILE_DIR:SkeerMidiVaultPlugin_VST3>/../Resources/moduleinfo.json"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/FixModuleInfo.cmake"
    COMMENT "Making the bundle's module info valid JSON"
    VERBATIM
)

# ---------------------------------------------------------------------------
# Loading the bundle the way a DAW does
#
# Pointed at the artefact tree, not at an installed copy: a test that read the installed
# bundle would measure the previous build and still report success.
# ---------------------------------------------------------------------------
juce_add_console_app(VaultHostTest
    PRODUCT_NAME "VaultHostTest")

target_sources(VaultHostTest PRIVATE tests/VaultHostTest.cpp)

target_compile_definitions(VaultHostTest PRIVATE
    ${VAULT_DEFINES}
    JUCE_PLUGINHOST_VST3=1
    # A console program runs no dispatch loop, and the asynchronous plugin entry points
    # report back on the message thread -- which never gets pumped here.
    JUCE_MODAL_LOOPS_PERMITTED=1
    # The emission check hands the loaded bundle a project state naming a real file from the demo
    # library. A host does not browse for it; it restores what a project saved, which is why the
    # path arrives as a compile definition rather than through a panel.
    SKEER_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../fixtures/demo_library"
    VAULT_VST3_BUNDLE="${CMAKE_CURRENT_BINARY_DIR}/SkeerMidiVaultPlugin_artefacts/$<CONFIG>/VST3/SKEER MIDI VAULT.vst3")

juce_generate_juce_header(VaultHostTest)

target_link_libraries(VaultHostTest
    PRIVATE
        juce::juce_audio_utils
        juce::juce_audio_processors
        # The emission block hashes the fixture it points the project at, so the state it hands the
        # bundle carries a digest the bytes on disk actually have.
        juce::juce_cryptography
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_warning_flags)

if (MSVC)
    # JUCE's own VST3 hosting source trips /W4 with C4458 when compiled into this target.
    # Third-party code, so the warning is quietened here instead of changing the flags every
    # other target shares.
    target_compile_options(VaultHostTest PRIVATE /wd4458)
endif()

add_dependencies(VaultHostTest SkeerMidiVaultPlugin_VST3)

# ---------------------------------------------------------------------------
# Where the index comes from
#
# Discovery is pure path arithmetic, so it is tested against four directories built in a
# temporary folder: the machine-wide install has to be proven findable on a machine that may
# not have one, and a check that quietly skips when the folder is absent proves nothing.
# ---------------------------------------------------------------------------
juce_add_console_app(VaultLocatorTest
    PRODUCT_NAME "VaultLocatorTest")

target_sources(VaultLocatorTest PRIVATE
    ${VAULT_CORE_SOURCES}
    tests/VaultLocatorTest.cpp)

target_include_directories(VaultLocatorTest PRIVATE Source)

target_compile_definitions(VaultLocatorTest PUBLIC ${VAULT_DEFINES})

juce_generate_juce_header(VaultLocatorTest)

target_link_libraries(VaultLocatorTest
    PRIVATE
        juce::juce_core
        # The core source list carries the reader too, and the reader is what pulls in SQLite.
        VaultSQLite
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_warning_flags)

add_test(NAME vault-locator-test COMMAND VaultLocatorTest)

# ---------------------------------------------------------------------------
# Reading the index
#
# The only target here that touches the user's data, so it is the one target that has to prove
# it cannot write. It builds its own fixture beside the exe, and the live half of the run
# prints a skip line instead of passing quietly on a machine with no index installed.
# ---------------------------------------------------------------------------
juce_add_console_app(VaultIndexTest
    PRODUCT_NAME "VaultIndexTest")

target_sources(VaultIndexTest PRIVATE
    ${VAULT_CORE_SOURCES}
    tests/VaultIndexTest.cpp)

target_include_directories(VaultIndexTest PRIVATE Source)

target_compile_definitions(VaultIndexTest PUBLIC ${VAULT_DEFINES})

juce_generate_juce_header(VaultIndexTest)

target_link_libraries(VaultIndexTest
    PRIVATE
        juce::juce_core
        juce::juce_cryptography
        VaultSQLite
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_warning_flags)

add_test(NAME vault-index-test COMMAND VaultIndexTest)

# ---------------------------------------------------------------------------
# Reading a source .mid
#
# The repo's demo library is the fixture set, and the shipped files are a harsher test of the
# parser than anything written here. The path arrives as a compile definition so the test runs
# from any working directory, and it fails loudly rather than skipping if the library is not
# where the repo says it is.
#
# This target also carries the index reader, because its last section asks both halves the same
# question -- is files.content_hash the digest of the bytes at that path? -- on the user's real
# library. That is the only claim here that needs reader and file in one program, so it is the
# reason SQLite is linked into a MIDI test.
# ---------------------------------------------------------------------------
juce_add_console_app(VaultMidiTest
    PRODUCT_NAME "VaultMidiTest")

target_sources(VaultMidiTest PRIVATE
    ${VAULT_CORE_SOURCES}
    ${VAULT_MIDI_SOURCES}
    tests/VaultMidiTest.cpp)

target_include_directories(VaultMidiTest PRIVATE Source)

target_compile_definitions(VaultMidiTest PUBLIC ${VAULT_DEFINES})

target_compile_definitions(VaultMidiTest PRIVATE
    SKEER_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../fixtures/demo_library")

juce_generate_juce_header(VaultMidiTest)

target_link_libraries(VaultMidiTest
    PRIVATE
        juce::juce_core
        juce::juce_audio_basics
        juce::juce_cryptography
        # The core source list carries the reader, and the reader is what pulls in SQLite.
        VaultSQLite
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_warning_flags)

add_test(NAME vault-midi-test COMMAND VaultMidiTest)

# ---------------------------------------------------------------------------
# Playing a clip
#
# The clock, the tempo switch, the transpose and the loop, tested against a transport this program
# writes itself: a synthetic host position per block, with numbers chosen so the expected sample
# offset is exact. The plug-in wrapper is in the binary too, because the parameter has to be shown
# to reach the clip and not only to exist next to it.
#
# Storage is linked here and the earlier comment saying it was not is now wrong, so it is replaced
# rather than left to mislead: since step 6 the processor's vtable names createEditor(), the editor
# browses the index, and a target that compiles the processor cannot link without the reader and
# SQLite. What this suite still asserts is time, not storage -- it never presses Connect and every
# transport is synthetic -- but the program is no longer one that cannot ask the index anything.
# ---------------------------------------------------------------------------
juce_add_console_app(VaultEmitTest
    PRODUCT_NAME "VaultEmitTest")

target_sources(VaultEmitTest PRIVATE
    ${VAULT_CORE_SOURCES}
    ${VAULT_MIDI_SOURCES}
    ${VAULT_EMIT_SOURCES}
    ${VAULT_EDITOR_SOURCES}
    Source/VaultMIDIProcessor.cpp
    tests/VaultEmitTest.cpp)

target_include_directories(VaultEmitTest PRIVATE Source)

target_compile_definitions(VaultEmitTest PUBLIC ${VAULT_DEFINES})

target_compile_definitions(VaultEmitTest PRIVATE
    SKEER_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../fixtures/demo_library")

juce_generate_juce_header(VaultEmitTest)

target_link_libraries(VaultEmitTest
    PRIVATE
        juce::juce_audio_processors
        juce::juce_audio_basics
        juce::juce_core
        juce::juce_cryptography
        # The editor's Connect path is in this binary (see the note above), and the reader is what
        # pulls in SQLite.
        VaultSQLite
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_warning_flags)

add_test(NAME vault-emit-test COMMAND VaultEmitTest)

# ---------------------------------------------------------------------------
# The front door, driven without a window
#
# The panel is the only part of this plug-in a producer touches, and the part no other suite here
# can reach: it needs a message thread, a widget tree, and an index that exists only in this test.
# So this program builds its own fixture folder -- an index *and* a real .mid copied out of the
# demo library, because a row whose path is not on disk cannot test a load -- points discovery at
# it through SKEER_MIDIVAULT_DATA, and drives the controls directly.
#
# Nothing is shown on screen and no window is created: no showTopLevelWindowOnScreen(), no peer,
# no desktop and no stolen focus. The checks are about behaviour, not pixels -- what the buttons
# do, what the index folder is left holding, and whether the strip says the true thing.
# ---------------------------------------------------------------------------
juce_add_console_app(VaultEditorTest
    PRODUCT_NAME "VaultEditorTest")

target_sources(VaultEditorTest PRIVATE
    ${VAULT_CORE_SOURCES}
    ${VAULT_MIDI_SOURCES}
    ${VAULT_EMIT_SOURCES}
    ${VAULT_EDITOR_SOURCES}
    Source/VaultMIDIProcessor.cpp
    tests/VaultEditorTest.cpp)

target_include_directories(VaultEditorTest PRIVATE Source)

target_compile_definitions(VaultEditorTest PUBLIC ${VAULT_DEFINES})

target_compile_definitions(VaultEditorTest PRIVATE
    SKEER_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../fixtures/demo_library"
    # Typing into a juce::TextEditor does not call onTextChange inline: textChanged() posts a
    # command message (juce_TextEditor.cpp:1304), so the panel's filter only re-queries when a
    # message loop runs. A console program has no loop, so this check pumps one for a few
    # milliseconds and the filter behaves as it does under a host. Without the macro the call is
    # compiled out and the check would be asserting a code path no host ever takes.
    JUCE_MODAL_LOOPS_PERMITTED=1)

juce_generate_juce_header(VaultEditorTest)

target_link_libraries(VaultEditorTest
    PRIVATE
        juce::juce_audio_processors
        juce::juce_audio_basics
        juce::juce_gui_basics
        juce::juce_core
        juce::juce_cryptography
        # The reader is what pulls SQLite in; the fixture is written with the same amalgamation.
        VaultSQLite
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_warning_flags)

add_test(NAME vault-editor-test COMMAND VaultEditorTest)

add_test(NAME vault-host-test COMMAND VaultHostTest)

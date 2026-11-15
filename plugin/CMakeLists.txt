cmake_minimum_required(VERSION 3.22)

project(SkeerMidiVaultPlugin VERSION 1.0.0 LANGUAGES C CXX)

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

set(VAULT_PLUGIN_SOURCES
    ${VAULT_CORE_SOURCES}
    ${VAULT_MIDI_SOURCES}
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
    PLUGIN_MANUFACTURER_CODE SkAu
    PLUGIN_CODE Mvlt
    # Derived from the target name, the default reads 'com.Skeer Audio.SkeerMidiVaultPlugin'
    # -- a space inside a reverse-DNS identifier, which JUCE warns about and macOS would not
    # accept. Spelling it out also keeps it stable if the product name is ever reworded.
    BUNDLE_ID com.skeeraudio.midivault
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT TRUE
    NEEDS_MIDI_OUTPUT TRUE
    IS_MIDI_EFFECT TRUE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    # The installer is the only thing that may place a bundle. Left TRUE, JUCE copies the
    # build straight into a scanned VST3 folder on every compile, which is exactly how a
    # second copy of one plugin comes to exist.
    COPY_PLUGIN_AFTER_BUILD FALSE
    FORMATS VST3
    PRODUCT_NAME "SKEER MIDI VAULT"
    VST3_CATEGORIES Fx)

# What this switch buys, measured: with it at its default, a host loading this bundle was
# offered 2083 parameters -- Follow Host Tempo, Transpose, Bypass and 16 channels x 130
# auto-published "MIDI CC ch|cc" controls. The emulation exists so a host can drive a
# plugin's MIDI *input* by automating parameters; this plugin reads notes, never remote-
# controlled CCs, and it produces CCs as output events, which need no parameter. So the
# 2080 controls would only ever be noise in a DAW's parameter list.
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
    VAULT_VST3_BUNDLE="${CMAKE_CURRENT_BINARY_DIR}/SkeerMidiVaultPlugin_artefacts/$<CONFIG>/VST3/SKEER MIDI VAULT.vst3")

juce_generate_juce_header(VaultHostTest)

target_link_libraries(VaultHostTest
    PRIVATE
        juce::juce_audio_utils
        juce::juce_audio_processors
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

add_test(NAME vault-host-test COMMAND VaultHostTest)

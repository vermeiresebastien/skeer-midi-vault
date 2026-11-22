# Configures, builds and then runs the six headless checks against the VST3 form of
# SKEER MIDI VAULT: where the index is (vault-locator-test), reading it without writing to it
# (vault-index-test), reading a source .mid (vault-midi-test), playing a clip on the host's clock
# (vault-emit-test), driving the editor panel without a window (vault-editor-test) and loading the
# bundle the way a DAW does and emitting through that wrapper (vault-host-test).
#
# JUCE is taken from a local checkout by default because a 100 MB shallow clone is the
# slowest possible way to find out whether a build works. CMakeLists.txt still declares
# FetchContent at tag 8.0.8, so a fresh clone with no -Juce argument builds on its own.
#
# Disclosed rather than smoothed over: the default checkout above is skulpt's and reports
# 8.0.4, while CMakeLists.txt asks FetchContent for 8.0.8, so the pair was measured against both.
# Both trees, measured 2026-11-16 with the command in the header above, gave identical counts --
# 15, 24+1 skipped, 35+1 skipped, 77, 136, 26 checks, none failed. Keep that habit on this line: the
# modules differed once already between those tags (MidiMessageSequence::size became getNumEvents).
#
# Measuring the second tag needs its own build directory. Reconfiguring the same one with a
# different -Juce fails inside JUCE: its nested juceaide project has already cached the first
# tree's CMakeLists.txt and refuses the second. -BuildDir build/tag-808 sits inside the ignored
# build tree, so the pair is compared without a stray directory showing up in git status.
#
#   powershell -File plugin/build.ps1
#   powershell -File plugin/build.ps1 -Juce D:/Projects/skeer-audio/skulpt/external/JUCE
#   powershell -File plugin/build.ps1 -BuildDir build/tag-808 -Juce D:/Projects/skeer-audio/pulsekit/build/_deps/juce-src

param(
    [string] $Juce = "D:/Projects/skeer-audio/skulpt/external/JUCE",
    [string] $Config = "Release",
    # Relative to this script, so the default is the same directory every existing invocation
    # already used and a second tree only gets a directory when one is asked for.
    [string] $BuildDir = "build"
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$build = Join-Path $here $BuildDir

cmake -S $here -B $build "-DFETCHCONTENT_SOURCE_DIR_JUCE=$Juce"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

cmake --build $build --config $Config
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# The version the shipping bundle reports about itself, read out of its bytes rather than out of the
# declaration that was supposed to reach them. This belongs here and not only in the release gate
# because this is the one command that produces the binary. See scripts\check_plugin_version.ps1.
& (Join-Path $PSScriptRoot "..\scripts\check_plugin_version.ps1") -Bundle (Join-Path $build "SkeerMidiVaultPlugin_artefacts\$Config\VST3\SKEER MIDI VAULT.vst3")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

ctest --test-dir $build -C $Config --output-on-failure
exit $LASTEXITCODE

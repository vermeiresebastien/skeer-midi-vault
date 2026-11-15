#pragma once

// Where the index lives. juce_core only, and deliberately not <JuceHeader.h>: discovery has
// to compile into the console checks as well as the plug-in, and a dependency on the generated
// header would drag the audio modules in with it.
#include <juce_core/juce_core.h>

#include <vector>

namespace vault
{

/** A data directory that holds an index, and the reason it was looked at. */
struct IndexCandidate
{
    juce::String directory;
    juce::String origin;
};

/** The four places an index may come from, named so a test can describe a machine it is
    not running on. */
struct IndexRoots
{
    juce::String environment;   // whatever SKEER_MIDIVAULT_DATA points at
    juce::String user;          // %LOCALAPPDATA%\Skeer\MIDI Vault
    juce::String machine;       // %PROGRAMDATA%\Skeer\MIDI Vault
    juce::String sideBySide;    // beside the bundle the plugin was loaded from

    static IndexRoots fromRuntime();
};

const juce::String& indexFileName();

/** Every root that actually holds an index, in priority order. */
std::vector<IndexCandidate> findIndexes (const IndexRoots&);

/** The one the plugin will read -- the first hit, or an empty string when there is none. */
juce::String resolveIndex (const IndexRoots&);

/** The directory beside a plugin binary where a colocated library would sit. Split out from
    fromRuntime() because it is string arithmetic over a path the runtime can only guess at,
    and a guess is not something to leave unchecked. */
juce::String sideBySideDirectoryFor (const juce::String& loadedModulePath);

} // namespace vault

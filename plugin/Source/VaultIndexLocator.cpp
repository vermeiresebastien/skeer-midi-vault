#include "VaultIndexLocator.h"

namespace vault
{

namespace
{

juce::String environmentVariable (const char* name)
{
    return juce::SystemStats::getEnvironmentVariable (name, {}).trim();
}

void addIfIndexed (std::vector<IndexCandidate>& out, const juce::String& directory,
                   const juce::String& origin)
{
    if (directory.isEmpty())
        return;

    const auto normalised = juce::File (directory).getFullPathName();

    if (juce::File (normalised).getChildFile (indexFileName()).existsAsFile())
        out.push_back ({ normalised, origin });
}

juce::String userProfileRoot()
{
    // The app builds its path from %LOCALAPPDATA% (midivault/server.py:_default_data_dir), so
    // that variable is read first here too: JUCE's userApplicationDataDirectory is CSIDL_APPDATA
    // -- the Roaming folder -- and a plugin that looked there would find an empty directory
    // while the user's 46,000-file index sat in Local.
    auto local = environmentVariable ("LOCALAPPDATA");

    if (local.isNotEmpty())
        return local;

   #if JUCE_WINDOWS
    return juce::File::getSpecialLocation (juce::File::windowsLocalAppData).getFullPathName();
   #else
    return juce::File::getSpecialLocation (juce::File::userHomeDirectory)
               .getChildFile (".local").getChildFile ("share").getFullPathName();
   #endif
}

juce::String machineRoot()
{
   #if JUCE_WINDOWS
    auto programData = environmentVariable ("PROGRAMDATA");

    if (programData.isNotEmpty())
        return programData;

    return juce::File::getSpecialLocation (juce::File::commonApplicationDataDirectory).getFullPathName();
   #else
    return {};
   #endif
}

} // namespace

const juce::String& indexFileName()
{
    static const juce::String name ("midivault.sqlite3");
    return name;
}

IndexRoots IndexRoots::fromRuntime()
{
    // The two installed folders keep the app's own Skeer\MIDI Vault tail, because that is the
    // directory the service writes. A plugin that invented its own name here would read a
    // second, never-updated index.
    const auto libraryTail = [] (juce::String root)
    {
        if (root.isEmpty())
            return root;

        return juce::File (root).getChildFile ("Skeer").getChildFile ("MIDI Vault").getFullPathName();
    };

    IndexRoots roots;
    roots.environment = environmentVariable ("SKEER_MIDIVAULT_DATA");
    roots.user        = libraryTail (userProfileRoot());
    roots.machine     = libraryTail (machineRoot());
    roots.sideBySide  = sideBySideDirectoryFor (
        juce::File::getSpecialLocation (juce::File::currentExecutableFile).getFullPathName());

    return roots;
}

juce::String sideBySideDirectoryFor (const juce::String& loadedModulePath)
{
    auto folder = juce::File (loadedModulePath).getParentDirectory();

    // A VST3 module lives inside its bundle, and the bundle is the ancestor named *.vst3:
    //   ...\VST3\Product.vst3\Contents\x86_64-win\Product.vst3
    //   ...\VST3\Product.vst3\Contents\MacOS\Product
    // "Beside the plugin" means beside that bundle, not beside the binary buried in it.
    for (int i = 0; i < 6 && folder.getParentDirectory() != folder; ++i)
    {
        if (folder.getFileExtension().equalsIgnoreCase (".vst3"))
            return folder.getParentDirectory().getChildFile ("SKEER MIDI VAULT").getFullPathName();

        folder = folder.getParentDirectory();
    }

    // Not a bundle -- the standalone build, or a test binary: beside whatever was launched.
    return juce::File (loadedModulePath).getParentDirectory()
               .getChildFile ("SKEER MIDI VAULT").getFullPathName();
}

std::vector<IndexCandidate> findIndexes (const IndexRoots& roots)
{
    std::vector<IndexCandidate> found;

    addIfIndexed (found, roots.environment, "SKEER_MIDIVAULT_DATA");
    addIfIndexed (found, roots.user,        "user profile");
    addIfIndexed (found, roots.machine,     "this machine");
    addIfIndexed (found, roots.sideBySide,  "beside the plugin");

    return found;
}

juce::String resolveIndex (const IndexRoots& roots)
{
    const auto found = findIndexes (roots);

    if (found.empty())
        return {};

    return juce::File (found.front().directory).getChildFile (indexFileName()).getFullPathName();
}

} // namespace vault

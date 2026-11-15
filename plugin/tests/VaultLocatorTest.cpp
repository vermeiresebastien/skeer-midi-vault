// The index discovery order, exercised against four directories this program made up.
//
// Which folder the plugin reads is the difference between the user hearing their library and
// hearing nothing, and it is invisible to every other check in this tree: the host test loads
// a bundle, the smoke test drives a processor, and neither one ever asks where the data came
// from. It is also the check that cannot be made against the user's real index, because a
// machine with no ProgramData install would silently skip it -- so the roots are injected, and
// a fake machine stands in for the real one.
//
// Exit code is the failure count clamped to 1, so ctest reads it directly.

#include <JuceHeader.h>

#include <cstdio>
#include <vector>

#include "VaultIndexLocator.h"

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

/** A directory holding what a directory must have to count as an index. */
juce::String makeIndex (const juce::File& directory)
{
    if (auto result = directory.createDirectory(); result.failed())
        std::printf ("FAIL  the fixture could not be written to %s: %s\n",
                     directory.getFullPathName().toRawUTF8(),
                     result.getErrorMessage().toRawUTF8());

    directory.getChildFile (vault::indexFileName()).replaceWithData ("fake", 4);

    return directory.getFullPathName();
}

juce::String originsOf (const std::vector<vault::IndexCandidate>& found)
{
    juce::String joined;

    for (const auto& candidate : found)
        joined += (joined.isEmpty() ? "" : ", ") + candidate.origin;

    return joined;
}

juce::String pathOf (const std::vector<vault::IndexCandidate>& found, int index)
{
    return index < static_cast<int> (found.size()) ? found[static_cast<size_t> (index)].directory
                                                   : juce::String ("<missing>");
}

} // namespace

int main()
{
    std::printf ("SKEER MIDI VAULT index discovery test\n===============================\n\n");

    // A scratch folder of this program's own, beside the binary rather than in %TEMP%: a
    // fixture nobody can write is the difference between nine FAILs about discovery and one
    // honest line about the sandbox. It is removed again on the way out.
    const auto sandbox = juce::File::getSpecialLocation (juce::File::currentExecutableFile)
                             .getParentDirectory().getChildFile ("midivault-locator-sandbox");

    sandbox.deleteRecursively();

    vault::IndexRoots fullRoots;
    fullRoots.environment = makeIndex (sandbox.getChildFile ("env"));
    fullRoots.user        = makeIndex (sandbox.getChildFile ("user/Skeer/MIDI Vault"));
    fullRoots.machine     = makeIndex (sandbox.getChildFile ("machine/Skeer/MIDI Vault"));
    fullRoots.sideBySide  = makeIndex (sandbox.getChildFile ("install/SKEER MIDI VAULT"));

    info ("sandbox: " + sandbox.getFullPathName());

    const auto all = vault::findIndexes (fullRoots);

    std::printf ("info  listed %d candidate(s): %s\n",
                 static_cast<int> (all.size()), originsOf (all).toRawUTF8());

    check (all.size() == 4, "all four roots are offered when all four hold an index");
    check (originsOf (all) == "SKEER_MIDIVAULT_DATA, user profile, this machine, beside the plugin",
           "in the promised order: override, user, machine, side-by-side");

    // The one the installer depends on: a machine-wide install has to be seen at all.
    check (pathOf (all, 2) == fullRoots.machine, "the machine-wide folder is listed, not just searched");

    check (vault::resolveIndex (fullRoots)
               == juce::File (fullRoots.environment).getChildFile (vault::indexFileName()).getFullPathName(),
           "the environment override outranks a user index and a machine index");

    vault::IndexRoots machineOnly;
    machineOnly.machine = makeIndex (sandbox.getChildFile ("alone/Skeer/MIDI Vault"));

    const auto alone = vault::findIndexes (machineOnly);

    check (alone.size() == 1 && alone.front().origin == "this machine",
           "a machine-wide index is found on a user who has none of their own");
    check (vault::resolveIndex (machineOnly)
               == juce::File (machineOnly.machine).getChildFile (vault::indexFileName()).getFullPathName(),
           "and it is the one the plugin opens");

    vault::IndexRoots gaps = fullRoots;

    gaps.environment = sandbox.getChildFile ("empty-env").getFullPathName();
    juce::File (gaps.environment).createDirectory();                       // folder there, no index
    gaps.user = sandbox.getChildFile ("never-created").getFullPathName();   // not even a folder

    const auto afterGaps = vault::findIndexes (gaps);

    std::printf ("info  with two roots empty, %d remain: %s\n",
                 static_cast<int> (afterGaps.size()), originsOf (afterGaps).toRawUTF8());

    check (afterGaps.size() == 2 && originsOf (afterGaps) == "this machine, beside the plugin",
           "a root without an index drops out and the rest keep their order");

    vault::IndexRoots nowhere;
    nowhere.user = sandbox.getChildFile ("nothing/here").getFullPathName();

    check (vault::findIndexes (nowhere).empty() && vault::resolveIndex (nowhere).isEmpty(),
           "with no index anywhere, nothing is claimed as a path");

    //=========================================================================
    // The side-by-side folder, derived from where the module was loaded from
    //=========================================================================
    const auto insideBundle = "C:/Program Files/Common Files/VST3/SKEER MIDI VAULT.vst3"
                              "/Contents/x86_64-win/SKEER MIDI VAULT.vst3";

    const auto beside = vault::sideBySideDirectoryFor (insideBundle);

    info ("loaded from the bundle, side-by-side is: " + beside);

    // JUCE canonicalises a path's separators on the way through File, so the expectation is
    // spelled the way Windows spells it.
    check (beside.equalsIgnoreCase ("C:\\Program Files\\Common Files\\VST3\\SKEER MIDI VAULT"),
           "beside a bundle means beside the .vst3, not beside the binary buried inside it");

    check (vault::sideBySideDirectoryFor ("D:\\tools\\VaultHostTest.exe")
               .equalsIgnoreCase ("D:\\tools\\SKEER MIDI VAULT"),
           "and beside a plain executable means next to it");

    //=========================================================================
    // The machine this runs on
    //=========================================================================
    const auto live = vault::IndexRoots::fromRuntime();

    info ("live user root:    " + live.user);
    info ("live machine root: " + live.machine);
    info ("live side-by-side: " + live.sideBySide);

    check (live.user.isNotEmpty() && live.machine.isNotEmpty(),
           "the running machine has both an installed folder and a machine folder to look in");

    check (live.user.containsIgnoreCase ("AppData") && ! live.user.containsIgnoreCase ("Roaming"),
           "the user folder is Local, where the service writes -- not Roaming");

    // The equality that matters is with the app's own expression, and the app's expression is
    // the variable. Where the variable is absent, JUCE's folder id is the fallback and there is
    // nothing to be equal to.
    const auto localAppData = juce::SystemStats::getEnvironmentVariable ("LOCALAPPDATA", {});

    if (localAppData.isNotEmpty())
    {
        check (live.user.equalsIgnoreCase (juce::File (localAppData)
                                               .getChildFile ("Skeer").getChildFile ("MIDI Vault")
                                               .getFullPathName()),
               "and it is byte for byte the folder midivault/server.py uses");
    }
    else
    {
        std::printf ("skip  %%LOCALAPPDATA%% is unset here, so there is no app path to compare against\n");
    }

    check (live.machine.isNotEmpty()
               && juce::File (live.machine).getParentDirectory().getFileName() == "Skeer"
               && live.machine.endsWithIgnoreCase ("MIDI Vault"),
           "the machine folder is <ProgramData>\\Skeer\\MIDI Vault");

    // The decisive one on a machine that has the app installed: the path the plugin works out
    // has to be the path the service actually writes. Printed as skipped where it cannot run,
    // so a green report always says which checks really happened.
    const auto realIndex = juce::File (live.user).getChildFile (vault::indexFileName());

    if (live.environment.isNotEmpty())
    {
        std::printf ("skip  SKEER_MIDIVAULT_DATA is set to %s on this machine, so the user"
                     " folder is legitimately not the answer here\n",
                     live.environment.toRawUTF8());
    }
    else if (realIndex.existsAsFile())
    {
        info ("real index: " + realIndex.getFullPathName()
              + " (" + juce::String (static_cast<juce::int64> (realIndex.getSize() / 1024 / 1024)) + " MB)");

        check (vault::resolveIndex (live).equalsIgnoreCase (realIndex.getFullPathName()),
               "on this machine the plugin resolves to the index the app is using");
    }
    else
    {
        std::printf ("skip  no index in the user folder on this machine, so live resolution did not run\n");
    }

    sandbox.deleteRecursively();

    std::printf ("\n%d checks, %d failed\n", checks, failures);
    return failures > 0 ? 1 : 0;
}

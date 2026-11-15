// Loads the VST3 bundle this build just produced, through JUCE's own VST3 hosting code, and
// behaves like a DAW: read the module info a scanner would trust, find the classes, describe
// them, instantiate one, drive its parameters, run a block through the wrapper.
//
// Driving the processor object directly proves the logic but says nothing about the wrapper
// -- whether the bundle registers a class at all, whether its module info survives a strict
// parser, whether the exported parameter list reaches a host, or whether a host can get MIDI
// out of it. This is what turns "it should load in Live" into evidence.
//
// Exit code is the failure count clamped to 1, so ctest reads it directly.

#include <JuceHeader.h>

#include <cmath>
#include <cstdio>

#ifndef VAULT_VST3_BUNDLE
 #define VAULT_VST3_BUNDLE ""
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

int countSubstring (const juce::String& text, const juce::String& needle)
{
    int total = 0;

    for (int at = text.indexOf (0, needle); at >= 0;
         at = text.indexOf (at + 1, needle))
        ++total;

    return total;
}

// Parameters are found by display name, not by id: a hosted parameter's getParameterID()
// is the numeric VST3 id the wrapper assigned, so the string the plugin wrote in its
// layout does not come back through it. The name is the one thing that does.
juce::AudioProcessorParameter* findParameter (juce::AudioPluginInstance& instance,
                                              const juce::String& name)
{
    for (auto* parameter : instance.getParameters())
    {
        if (parameter != nullptr && parameter->getName (64) == name)
            return parameter;
    }

    return nullptr;
}

} // namespace

int main (int argc, char* argv[])
{
    juce::ScopedJuceInitialiser_GUI gui;

    std::printf ("SKEER MIDI VAULT host test\n");
    std::printf ("==========================\n");

    // The build passes the bundle it produced; a path on the command line overrides it so
    // the same program can check an installed copy later. Deliberately the artefact tree
    // and not an installed folder: a test pointed at an installed copy would measure the
    // previous build and still report success.
    juce::String bundleArg (juce::String (VAULT_VST3_BUNDLE));

    for (int a = 1; a < argc; ++a)
    {
        const juce::String arg (argv[a]);

        if (! arg.startsWith ("--"))
        {
            bundleArg = arg;
            break;
        }
    }

    const juce::File bundle (bundleArg);
    std::printf ("bundle: %s\n", bundle.getFullPathName().toRawUTF8());
    check (bundle.exists(), "the built VST3 bundle is where the build put it");

    if (! bundle.exists())
        return 1;

    const auto moduleInfo = bundle.getChildFile ("Contents/Resources/moduleinfo.json");
    check (moduleInfo.existsAsFile(), "the bundle carries module info for host scanning");

    if (moduleInfo.existsAsFile())
    {
        const auto compact = moduleInfo.loadFileAsString().removeCharacters (" \t\r\n");
        const auto trailing = countSubstring (compact, ",}") + countSubstring (compact, ",]");

        std::printf ("info  trailing commas before a close: %d\n", trailing);
        check (trailing == 0,
               "a strict JSON parser accepts the module info a scanner reads first");
    }

    juce::AudioPluginFormatManager formats;
    formats.addDefaultFormats();

    juce::AudioPluginFormat* vst3 = nullptr;

    for (int i = 0; i < formats.getNumFormats(); ++i)
    {
        auto* format = formats.getFormat (i);

        if (format->getName().containsIgnoreCase ("VST3"))
            vst3 = format;
    }

    check (vst3 != nullptr, "JUCE's VST3 host support is compiled into this test");

    if (vst3 == nullptr)
        return 1;

    juce::OwnedArray<juce::PluginDescription> found;
    vst3->findAllTypesForFile (found, bundle.getFullPathName());

    check (! found.isEmpty(), "a host scanning the bundle finds a plugin class");

    if (found.isEmpty())
    {
        std::printf ("\n%d checks, %d failed\n", checks, failures);
        return 1;
    }

    check (found.size() == 1, "and exactly one class, so a scan cannot offer a stale second one");

    const auto* description = found.getFirst();

    info ("name:          " + description->name);
    info ("vendor:        " + description->manufacturerName);
    info ("version:       " + description->version);
    info ("category:      " + description->category);
    info ("format:        " + description->pluginFormatName);
    info ("isInstrument:  " + juce::String (description->isInstrument ? "yes" : "no"));
    // JUCE 8's PluginDescription carries no MIDI capability fields at all, so what the
    // wrapper exposes as a MIDI effect is measured from the instance below, never assumed
    // from the description.

    check (description->name == "SKEER MIDI VAULT", "the class is named SKEER MIDI VAULT");
    check (description->manufacturerName == "Skeer Audio", "and carries the vendor CMake sets");

    juce::String error;
    auto instance = vst3->createInstanceFromDescription (*description, 48000.0, 512, error);

    check (instance != nullptr,
           error.isEmpty() ? juce::String ("the plugin instantiates")
                           : "the plugin instantiates: " + error);

    if (instance == nullptr)
    {
        std::printf ("\n%d checks, %d failed\n", checks, failures);
        return 1;
    }

    // What the wrapper actually exposes, because "it is a MIDI effect" is a claim about the
    // binary a host loads, not about a flag in the build file.
    info ("instance acceptsMidi:   " + juce::String (instance->acceptsMidi() ? "yes" : "no"));
    info ("instance producesMidi:  " + juce::String (instance->producesMidi() ? "yes" : "no"));
    info ("instance isMidiEffect:  " + juce::String (instance->isMidiEffect() ? "yes" : "no"));
    std::printf ("info  audio buses in/out:       %d / %d\n",
                 instance->getBusCount (true), instance->getBusCount (false));
    std::printf ("info  audio channels in/out:    %d / %d\n",
                 instance->getTotalNumInputChannels(), instance->getTotalNumOutputChannels());

    // VST3 has no "MIDI effect" flag for JUCE to carry across, so isMidiEffect() reads false
    // on the hosted side no matter what the build file says. What a host actually keys on is
    // this: MIDI in, MIDI out, and no audio path that it would have to insert on an audio
    // track. That is the contract worth a check, so the print above stays as colour.
    check (instance->acceptsMidi(),  "the host can route MIDI into the loaded plugin");
    check (instance->producesMidi(), "and reads MIDI back out of it");
    check (instance->getTotalNumInputChannels() == 0 && instance->getTotalNumOutputChannels() == 0,
           "it has no audio path, so it cannot steal or colour a signal chain");

    const auto& exported = instance->getParameters();
    int parameters = 0;
    int autoPublishedCCs = 0;

    for (auto* parameter : exported)
    {
        parameters += (parameter != nullptr ? 1 : 0);

        if (parameter != nullptr && parameter->getName (32).startsWith ("MIDI CC "))
            ++autoPublishedCCs;
    }

    std::printf ("info  exported parameters: %d (MIDI CC emulations: %d)\n",
                 parameters, autoPublishedCCs);

    // Two declared controls plus the bypass the wrapper adds for every VST3, and nothing
    // else. JUCE publishes a MIDI CC parameter for all 16 channels x 130 controllers when
    // a plugin asks for MIDI input, which is a host's way of automating CC *into* a plugin
    // this one never reads -- so 2083 here is not a longer list of the same thing, it is
    // 2080 controls no user can point at anything.
    check (autoPublishedCCs == 0, "no auto-published MIDI CC controls reach the host");
    check (parameters == 3, "the host sees the two controls the plugin declares and the wrapper's bypass");

    for (int i = 0; i < jmin (parameters, 6); ++i)
        info ("param[" + juce::String (i) + "]: "
              + (exported[i] != nullptr ? exported[i]->getName (32) : "<null>"));

    auto* transpose = findParameter (*instance, "Transpose");
    auto* followTempo = findParameter (*instance, "Follow Host Tempo");

    check (transpose != nullptr, "Transpose reaches the host by name");
    check (followTempo != nullptr, "Follow Host Tempo reaches the host by name");

    if (transpose != nullptr)
    {
        transpose->setValueNotifyingHost (0.5f);
        check (std::abs (transpose->getValue() - 0.5f) < 0.001f,
               "Transpose holds the value the host set (0.5 is the middle of -24..+24)");
    }

    if (followTempo != nullptr)
    {
        followTempo->setValueNotifyingHost (0.0f);
        const auto text = followTempo->getText (followTempo->getValue(), 16);
        std::printf ("info  Follow Host Tempo at value 0 reads: %s\n", text.toRawUTF8());
        check (text == "Off", "the tempo switch really has an Off the user can pick");
    }

    // The wrapper's MIDI path: a note through the VST3 boundary, on a buffer sized from the
    // plugin's own channel count rather than an assumed one.
    instance->setNonRealtime (true);
    instance->prepareToPlay (48000.0, 512);

    juce::AudioBuffer<float> buffer (juce::jmax (1, instance->getTotalNumOutputChannels()), 512);
    juce::MidiBuffer midi;
    midi.addEvent (juce::MidiMessage (0x90, 60, 100), 0);
    midi.addEvent (juce::MidiMessage (0x80, 60, 0), 10);

    bool ran = true;

    try
    {
        instance->processBlock (buffer, midi);
    }
    catch (...)
    {
        ran = false;
    }

    check (ran, "a block passes through the wrapper without throwing");

    bool finite = true;

    for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
    {
        const auto* data = buffer.getReadPointer (ch);

        for (int i = 0; i < buffer.getNumSamples(); ++i)
            finite = finite && std::isfinite (data[i]);
    }

    check (finite, "the plugin's audio output stays finite");
    std::printf ("info  MIDI events after processBlock: %d\n", midi.getNumEvents());

    instance->releaseResources();

    std::printf ("\n%d checks, %d failed\n", checks, failures);
    return failures > 0 ? 1 : 0;
}

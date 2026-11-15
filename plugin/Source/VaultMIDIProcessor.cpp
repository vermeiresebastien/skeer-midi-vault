#include "VaultMIDIProcessor.h"

// The host's tempo is the useful default, but it is a switch and not a silent
// compensation: turning it off has to be something the user can see and pick, the same way
// every other automatic behaviour in this product is overridable.

juce::AudioProcessorValueTreeState::ParameterLayout VaultMIDIProcessor::createParameterLayout()
{
    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    layout.add (std::make_unique<juce::AudioParameterChoice> (
        juce::ParameterID { "followHostTempo", 1 }, "Follow Host Tempo",
        juce::StringArray { "Off", "On" }, 1));

    layout.add (std::make_unique<juce::AudioParameterInt> (
        juce::ParameterID { "transpose", 1 }, "Transpose", -24, 24, 0));

    return layout;
}

VaultMIDIProcessor::VaultMIDIProcessor()
    : AudioProcessor (BusesProperties()),
      valueTreeState (*this, nullptr, juce::Identifier ("VaultMIDI"), createParameterLayout())
{
}

VaultMIDIProcessor::~VaultMIDIProcessor() = default;

void VaultMIDIProcessor::prepareToPlay (double, int)
{
}

void VaultMIDIProcessor::releaseResources()
{
}

void VaultMIDIProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    // Pass-through for now: whatever the host sent stays exactly as it was, and nothing
    // here has ever touched a sample. BusesProperties() declares no audio buses, so the
    // wrapper is the one deciding that this plugin moves MIDI and nothing else.
    buffer.clear();
}

juce::AudioProcessorEditor* VaultMIDIProcessor::createEditor()
{
    return nullptr;
}

void VaultMIDIProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    auto state = valueTreeState.copyState();
    std::unique_ptr<juce::XmlElement> xml (state.createXml());
    copyXmlToBinary (*xml, destData);
}

void VaultMIDIProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    std::unique_ptr<juce::XmlElement> xml (getXmlFromBinary (data, sizeInBytes));

    if (xml != nullptr && xml->hasTagName (valueTreeState.state.getType()))
        valueTreeState.replaceState (juce::ValueTree::fromXml (*xml));
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new VaultMIDIProcessor();
}

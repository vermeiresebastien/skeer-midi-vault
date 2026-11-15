#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

// The VST3 form of MIDI VAULT: a MIDI effect that browses the local index and hands the
// selected file to the host. This class is the toolchain spike -- the transport is a
// pass-through and the two parameters are not read by anything yet, because the point of
// this step is only to prove that a bundle builds here, that its module info survives a
// strict parser, and that a host can load it, see its parameters and run it.
class VaultMIDIProcessor : public juce::AudioProcessor
{
public:
    VaultMIDIProcessor();
    ~VaultMIDIProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;

    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return false; }

    const juce::String getName() const override { return "SKEER MIDI VAULT"; }

    bool acceptsMidi() const override { return true; }
    bool producesMidi() const override { return true; }
    bool isMidiEffect() const override { return true; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    juce::AudioProcessorValueTreeState valueTreeState;

private:
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (VaultMIDIProcessor)
};

# Removes the trailing commas from a VST3 bundle's moduleinfo.json.
#
# The VST3 SDK's module-info generator writes them, and they make the file invalid JSON.
# moduleinfo.json exists so a host can list and describe a plugin *without loading its
# binary*, so a host with a strict parser either skips the plugin or falls back to a full
# scan -- and skipping is not an error dialog, it is the plugin quietly never appearing in
# the browser. JUCE's own parser is forgiving, which is why every JUCE-driven check stays
# green while a real host shows nothing.
#
# Ported from pulsekit/cmake/FixModuleInfo.cmake, itself ported from skulpt/cmake, where
# the same build step has protected two other products for longer than this one has existed.
#
# Usage: cmake -DVC_FILE=<path to moduleinfo.json> -P FixModuleInfo.cmake

if(NOT DEFINED VC_FILE)
    message(FATAL_ERROR "FixModuleInfo.cmake needs VC_FILE")
endif()

if(NOT EXISTS "${VC_FILE}")
    message(STATUS "FixModuleInfo: no file at ${VC_FILE}")
    return()
endif()

file(READ "${VC_FILE}" contents)
set(fixed "${contents}")

# One pass removes one level of nesting, so repeat until nothing changes: the file has a
# bare comma before a closing brace or bracket at several depths. Written as two
# escaped-literal patterns rather than one with a capture group, because the grouped form
# `,([}\\]])` looks right and silently matches nothing here.
set(previous "")
while(NOT fixed STREQUAL previous)
    set(previous "${fixed}")
    string(REGEX REPLACE ",[ \t\r\n]*\\}" "}" fixed "${fixed}")
    string(REGEX REPLACE ",[ \t\r\n]*\\]" "]" fixed "${fixed}")
endwhile()

if(NOT fixed STREQUAL contents)
    file(WRITE "${VC_FILE}" "${fixed}")
    message(STATUS "Removed the trailing commas from ${VC_FILE}")
else()
    message(STATUS "No trailing commas in ${VC_FILE}")
endif()

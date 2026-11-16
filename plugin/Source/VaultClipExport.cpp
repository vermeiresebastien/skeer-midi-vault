#include "VaultClipExport.h"

#include <juce_cryptography/juce_cryptography.h>

namespace vault
{

namespace
{

/** Windows compares paths case-insensitively and follows junctions and shortcuts under one name;
    a rule about not touching a file has to answer the same way the filesystem does, or "the same
    path" is all a caller gets to be wrong about. */
juce::File resolved (const juce::File& file)
{
    return file.isSymbolicLink() ? file.getLinkedTarget() : file;
}

/** The re-hash: the digest of what is on disk at `target` right now.

    `limit` of 0 reads the whole file, which is every production call. The header says why a
    shorter read exists; what matters here is that every branch of it can only report fewer bytes
    than are really there, never more, so a caller cannot use it to make a mismatch look like a
    match. A target that is gone, or that will not open, hashes as nothing -- which is a mismatch,
    and the right answer: nothing at the target is not the clip. */
juce::String readBackHash (const juce::File& target, size_t limit)
{
    if (! target.existsAsFile())
        return {};

    if (limit == 0)
        return juce::SHA256 (target).toHexString();

    auto stream = target.createInputStream();
    if (stream == nullptr)
        return {};

    juce::MemoryBlock landed;
    const auto bytesRead = stream->readIntoMemoryBlock (landed, static_cast<juce::ssize_t> (limit));

    return juce::SHA256 (landed.getData(), bytesRead).toHexString();
}

} // namespace

ClipCopyResult copyClipVerbatim (const juce::File& source, const juce::File& target,
                                 bool overwriteExisting, size_t verifyByteLimit)
{
    ClipCopyResult result;

    if (! source.existsAsFile())
    {
        result.outcome = ClipCopyOutcome::sourceMissing;
        result.message = "there is no file at " + source.getFullPathName();
        return result;
    }

    if (resolved (source).getFullPathName().equalsIgnoreCase (resolved (target).getFullPathName()))
    {
        result.outcome = ClipCopyOutcome::samePath;
        result.message = "that is the file the clip is playing from, and a source .mid is never "
                         "written; choose another name";
        return result;
    }

    // Before anything is read or written, and before the overwrite question: a 0-byte source is not
    // a copy that lands empty, it is a delete. juce_File.cpp:777 turns numberOfBytes == 0 into
    // deleteFile(), so without this branch "save this clip over that file" would remove the file the
    // user just named in the save dialog and then report a hash mismatch as if the copy had gone
    // wrong. An empty clip has no bytes to give anyone, so the answer is a refusal that says the
    // target was left alone -- and it is the only branch that could keep that promise.
    if (source.getSize() == 0)
    {
        result.outcome = ClipCopyOutcome::sourceEmpty;
        result.message = "the clip's file is empty (0 bytes), so there are no bytes to copy. "
                         "Nothing was written and " + target.getFullPathName() + " was left alone";
        return result;
    }

    if (! overwriteExisting && target.exists())
    {
        result.outcome = ClipCopyOutcome::targetExists;
        result.message = target.getFullPathName() + " already exists";
        return result;
    }

    juce::MemoryBlock bytes;

    if (! source.loadFileAsData (bytes))
    {
        result.outcome = ClipCopyOutcome::readFailed;
        result.message = "could not read " + source.getFullPathName();
        return result;
    }

    if (! target.replaceWithData (bytes.getData(), bytes.getSize()))
    {
        result.outcome = ClipCopyOutcome::writeFailed;
        result.message = "could not write " + target.getFullPathName();
        return result;
    }

    result.bytes        = static_cast<juce::int64> (bytes.getSize());
    result.sourceHash   = juce::SHA256 (bytes.getData(), bytes.getSize()).toHexString();
    result.writtenHash  = readBackHash (target, verifyByteLimit);

    if (result.writtenHash != result.sourceHash)
    {
        result.outcome = ClipCopyOutcome::bytesDiffer;
        result.message = "the file at " + target.getFullPathName()
                       + " is not byte-identical to the clip (source "
                       + result.sourceHash.substring (0, 12) + ", written "
                       + result.writtenHash.substring (0, 12) + ")";
        return result;
    }

    result.outcome = ClipCopyOutcome::wrote;
    result.message = target.getFullPathName();
    return result;
}

} // namespace vault

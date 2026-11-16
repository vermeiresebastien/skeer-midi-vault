#pragma once

#include <juce_core/juce_core.h>

namespace vault
{

/** Why a clip copy did or did not land. Each refusal is a different sentence to the user, so they
    are different outcomes rather than one false. */
enum class ClipCopyOutcome
{
    wrote,          // the target holds the source's bytes, byte for byte
    sourceMissing,  // nothing at the source path
    samePath,       // the target resolves to the file the clip is playing from
    sourceEmpty,    // the source is a 0-byte file, so there are no bytes to copy and writing it
                    // would have deleted the target -- see the replaceWithData note below
    targetExists,   // something is already there and no human confirmed replacing it
    readFailed,
    writeFailed,
    bytesDiffer,    // the write landed, but what landed is not the source's bytes
};

struct ClipCopyResult
{
    ClipCopyOutcome outcome = ClipCopyOutcome::writeFailed;
    juce::String message;           // in words, for the panel's status strip
    juce::String sourceHash;        // SHA-256 of the bytes read, lowercase hex
    juce::String writtenHash;       // SHA-256 of what is on disk at the target afterwards
    juce::int64 bytes = 0;
};

/** Writes a *copy* of a clip's bytes where the user points, and nowhere else.

    Verbatim on purpose: the source is read as bytes and written as bytes, never parsed and
    re-encoded. juce::MidiFile::writeTo closes open notes, and measured across the demo library it
    adds the same note-offs again on every pass (see VaultMidiSource's header: 149, 170, 191, 212),
    so a re-encode is a different file under the same name -- and the index's digest, which is what
    ties this row to these bytes, would stop matching it. The only file this function may create or
    replace is `target`.

    The three refusals are this function's job, not the caller's, so that no caller can forget them:

      - `target` may not resolve to `source`. That is the file being played, and the rule this
        product runs under is that a source .mid is never written -- a rename, a truncation or a
        rewrite behind the user's back included. Links are followed and the comparison ignores
        case, because on Windows two spellings are one file.
      - `source` may not be empty. See the replaceWithData paragraph: a 0-byte clip is not a
        missing write, it is a delete wearing a write's clothes.
      - an existing file is replaced only when `overwriteExisting` says a human confirmed it.

    `File::replaceWithData` is what writes, not a FileOutputStream: JUCE's FileOutputStream opens
    with OPEN_ALWAYS and seeks to the end of the file on Windows, so writing over an existing clip
    that way appends to it and the result no longer parses. Two things about `replaceWithData` are
    load-bearing here, both measured against the vendored source and identical on the two JUCE
    trees this lane builds on (juce_File.cpp:777-786): a zero length is turned into `deleteFile()`
    before anything is written, and `appendData`'s return value is discarded on the way in. The
    first is why the empty source is refused; the second is why the write is not trusted.

    After writing, the bytes that landed are hashed again and compared with the source's digest:
    "the copy is the clip" is the claim, and it is measured rather than assumed. That re-hash is the
    last defence in this function -- `overwriteTargetFileWithTemporary` retries the rename up to
    five times, so a target that lands short of the source's length is a reachable state, and only
    this comparison would say so.

    @param verifyByteLimit  how many bytes of the target the re-hash reads. 0 means the whole file,
        which is what every production call uses, and it is the default. A positive limit exists
        for one reason: the file system will not hand a headless suite a write that lands short --
        the rename either moves the whole file or fails -- so the only way to prove the re-hash
        decides the outcome is to let the suite read back fewer bytes than were written. A limit can
        only shrink what is compared, so it can only ever make this refuse; it is not a route to
        talking a mismatch into a match.
*/
ClipCopyResult copyClipVerbatim (const juce::File& source, const juce::File& target,
                                 bool overwriteExisting, size_t verifyByteLimit = 0);

} // namespace vault

# SQLite, vendored

`sqlite3.c` and `sqlite3.h`, version **3.54.1**, from the official amalgamation:

    https://www.sqlite.org/2026/sqlite-amalgamation-3540100.zip

Downloaded 2026-11-15; the archive itself was 2,990,966 bytes and is no longer kept. sqlite.org
publishes its digest as SHA3-256 (not SHA-256):

    SHA3-256  92281c86e2957f9b9305890f9ac04204caa7b677cc868dc326d942689df28e30

That digest was checked against the one printed on https://www.sqlite.org/download.html before
these two files were copied out of the archive. The archive is gone, so that check is a record
rather than something this tree can re-run; what it *can* re-run is the version, and it agrees:

    #define SQLITE_VERSION  "3.54.1"          sqlite3.h:149
    9,582,521 bytes  sqlite3.c  (271,131 lines)
      695,729 bytes  sqlite3.h  ( 14,447 lines)

`shell.c` and `sqlite3ext.h` were left behind: this product embeds a library, it does not ship a
command-line client.

## Why it is here as source

The index is SQLite, written by the Python service. JUCE 8 removed `juce_database`, so there is
no bundled way to read it, and the plugin must read it in the DAW without the service running.
Linking a prebuilt `sqlite3.lib` from someone's vcpkg cache would put a binary nobody can
attribute into an installer. The amalgamation is two files, one digest, and the whole build is
auditable.

The reader is **ahead** of the writer on purpose: the user's current index records SQLite
3.49.1 in its header (bytes 96-99), and 3.54.1 reads every older format. Upgrading this file is
always safe; downgrading it is not.

## Rules for these files

- Never edit them. They are not ours to patch.
- Upgrade by re-downloading, re-verifying the digest against sqlite.org, and replacing both
  files in the same commit.
- Compile flags live in `plugin/CMakeLists.txt` (target `VaultSQLite`), not here.
- The plugin opens this library **read-only** against the user's index. See
  `plugin/Source/VaultIndexReader.h` for what that means in practice, including the sidecar
  files a read-only open still creates.

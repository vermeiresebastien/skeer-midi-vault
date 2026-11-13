"""Windows-aware local drive discovery and safe file-system traversal helpers."""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

DRIVE_KINDS = {
    0: "unknown",
    1: "unavailable",
    2: "removable",
    3: "fixed",
    4: "network",
    5: "optical",
    6: "ramdisk",
}

# Windows file attribute bits used to avoid hydrating cloud placeholders and to
# avoid following junctions / symlinks. Unknown/zero on other platforms.
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000

_PROTECTED_DIR_NAMES = {
    "$recycle.bin", "system volume information", "$winreagent", "config.msi",
    "recovery", "windows", "program files", "program files (x86)",
    "programdata", "perflogs",
}

if sys.platform == "win32":
    _kernel32 = ctypes.windll.kernel32
    _GetLogicalDrives = _kernel32.GetLogicalDrives
    _GetDriveTypeW = _kernel32.GetDriveTypeW
    _GetVolumeInformationW = _kernel32.GetVolumeInformationW
    _GetDiskFreeSpaceExW = _kernel32.GetDiskFreeSpaceExW
    try:
        _mpr = ctypes.windll.mpr
        _WNetGetConnectionW = _mpr.WNetGetConnectionW
    except Exception:
        _mpr = None
        _WNetGetConnectionW = None
else:
    _kernel32 = None
    _mpr = None
    _WNetGetConnectionW = None


_CLOUD_LABEL_MARKERS = (
    "@", "onedrive", "google drive", "dropbox", "icloud", "box.com", "pcloud",
    "mega", "nextcloud", "sharepoint", "webdav", "cloud",
)


def _optional_source(kind: str, label: str) -> bool:
    if kind in ("removable", "network", "optical"):
        return True
    lowered = (label or "").casefold()
    # Some cloud-mount tools expose an account-labelled fixed virtual drive.
    # Treat those as optional so a Scan computer action does not silently pull
    # a large remote library; the user can still opt in.
    return any(marker in lowered for marker in _CLOUD_LABEL_MARKERS)


def _mapped_network_unc(root: str) -> str | None:
    """Detect a mapped network drive even when Windows reports DRIVE_FIXED.

    Some cloud-mount tools and remapped shares present as fixed local drives.
    The Win32 network provider still knows their UNC target in most mapped-share
    cases. Detection is best effort; the user can always deselect the source.
    """
    if not _WNetGetConnectionW:
        return None
    try:
        local_name = root[:2]
        buffer = ctypes.create_unicode_buffer(1024)
        length = wintypes.DWORD(len(buffer))
        result = _WNetGetConnectionW(
            ctypes.c_wchar_p(local_name),
            buffer,
            ctypes.byref(length),
        )
        if result == 0 and buffer.value:
            return buffer.value
    except Exception:
        return None
    return None


def _volume_info(root: str) -> dict:
    info = {"label": "", "filesystem": "", "total_bytes": None, "free_bytes": None}
    if not _kernel32:
        return info
    try:
        label_buf = ctypes.create_unicode_buffer(261)
        fs_buf = ctypes.create_unicode_buffer(261)
        serial = wintypes.DWORD()
        max_component = wintypes.DWORD()
        flags = wintypes.DWORD()
        ok = _GetVolumeInformationW(
            ctypes.c_wchar_p(root),
            label_buf, wintypes.DWORD(len(label_buf)),
            ctypes.byref(serial), ctypes.byref(max_component), ctypes.byref(flags),
            fs_buf, wintypes.DWORD(len(fs_buf)),
        )
        if ok:
            info["label"] = label_buf.value
            info["filesystem"] = fs_buf.value
        free = ctypes.c_ulonglong()
        total = ctypes.c_ulonglong()
        total_free = ctypes.c_ulonglong()
        ok_space = _GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(root),
            ctypes.byref(free), ctypes.byref(total), ctypes.byref(total_free),
        )
        if ok_space:
            info["total_bytes"] = int(total.value)
            info["free_bytes"] = int(free.value)
    except Exception:
        pass
    return info


def discover_drives() -> list[dict]:
    """Return mounted drives visible to this process, including optional kinds.

    Removable/network/optical drives are returned but are not enabled by
    default in the database layer.
    """
    drives: list[dict] = []
    if sys.platform != "win32":
        root = os.path.abspath(os.sep)
        drives.append({
            "path": root,
            "label": "File system root",
            "kind": "fixed",
            "drive_letter": None,
            "optional": False,
            "available": True,
            "total_bytes": None,
            "free_bytes": None,
            "filesystem": "",
        })
        return drives
    try:
        mask = _GetLogicalDrives()
    except Exception:
        mask = 0
    for index in range(26):
        if not mask & (1 << index):
            continue
        letter = chr(ord("A") + index)
        root = f"{letter}:\\"
        try:
            drive_type = _GetDriveTypeW(ctypes.c_wchar_p(root))
        except Exception:
            drive_type = 0
        if drive_type in (0, 1):
            continue
        kind = DRIVE_KINDS.get(drive_type, "unknown")
        mapped_unc = _mapped_network_unc(root)
        if mapped_unc and kind not in ("network", "removable", "optical"):
            kind = "network"
        info = _volume_info(root)
        available = bool(info["label"] or info["total_bytes"] is not None)
        if kind == "network":
            available = True  # a mapped disconnected share is still a remembered source
        display_label = info["label"] or f"Local Disk ({letter}:)"
        drives.append({
            "path": root,
            "label": display_label,
            "kind": kind,
            "drive_letter": letter,
            "optional": _optional_source(kind, display_label),
            "available": available,
            "total_bytes": info["total_bytes"],
            "free_bytes": info["free_bytes"],
            "filesystem": info["filesystem"],
            "network_path": mapped_unc,
        })
    return drives


def _norm(path: str | os.PathLike) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))


def is_protected(path: str) -> bool:
    """True for OS/protected system locations that should never be walked."""
    normalised = _norm(path)
    parts = Path(normalised).parts
    # Remove the drive root from consideration.
    for part in parts[1:]:
        if part.casefold() in _PROTECTED_DIR_NAMES:
            return True
    if sys.platform == "win32":
        env = os.environ
        for key in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            base = env.get(key)
            if base and (normalised == _norm(base) or normalised.startswith(_norm(base) + os.sep)):
                return True
    return False


def is_excluded(path: str, excludes: list[str]) -> bool:
    if not excludes:
        return False
    normalised = _norm(path)
    for exclude in excludes:
        if not exclude:
            continue
        candidate = _norm(exclude)
        if normalised == candidate or normalised.startswith(candidate + os.sep):
            return True
    return False


def is_link_or_junction(entry: os.DirEntry) -> bool:
    try:
        if entry.is_symlink():
            return True
        stat = entry.stat(follow_symlinks=False)
        attributes = getattr(stat, "st_file_attributes", 0)
        return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False


def is_cloud_placeholder(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(
        attributes
        & (FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)
    )


def is_offline_file(path: str) -> bool:
    try:
        stat = os.stat(path)
    except OSError:
        return False
    return is_cloud_placeholder(stat)


def safe_dir_key(path: str) -> tuple[int, int] | str:
    try:
        stat = os.stat(path, follow_symlinks=False)
        inode = getattr(stat, "st_ino", 0)
        device = getattr(stat, "st_dev", 0)
        if inode:
            return int(device), int(inode)
    except OSError:
        pass
    return _norm(path)


def path_is_within(path: str, root: str) -> bool:
    normalised = _norm(path)
    root_n = _norm(root)
    return normalised == root_n or normalised.startswith(root_n + os.sep)


def relative_display_path(path: str) -> str:
    """Best-effort short display path without assuming a common root."""
    try:
        return str(Path(path))
    except Exception:
        return path

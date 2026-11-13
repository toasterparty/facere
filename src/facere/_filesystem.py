"""What a stat leaves out about a file: whether its file system's timestamps can vouch for its content, and on Windows, when it last changed."""

import os
import sys

# Linux's names, as /proc/self/mountinfo gives them, for file systems whose timestamps prove nothing: network ones, whose clients
# cache attributes and whose servers keep their own clocks, and FAT, which stores coarse times. Every FUSE type counts too.
_UNTRUSTED_LINUX_TYPES = frozenset(
    {
        "nfs",
        "nfs4",
        "cifs",
        "smb3",
        "smbfs",
        "ncpfs",
        "ceph",
        "afs",
        "coda",
        "lustre",
        "gfs2",
        "ocfs2",
        "orangefs",
        "glusterfs",
        "vfat",
        "msdos",
        "fat",
        "exfat",
    }
)
_UNTRUSTED_WINDOWS_NAMES = frozenset({"FAT", "FAT12", "FAT16", "FAT32", "EXFAT"})
_MOUNTINFO = "/proc/self/mountinfo"
_MOUNTINFO_FIELDS_SEPARATOR = "-"


class FileSystems:
    """What each file system an invocation meets can vouch for, looked up once per device."""

    def __init__(self) -> None:
        self._trust_by_device: dict[int, bool] = {}
        self._linux_types: dict[int, str] | None = None

    def is_trusted(self, path: str, info: os.stat_result) -> bool:
        """Say whether a stat of the file at `path`, which `info` describes, shows every change to it: false on a network file system, any FUSE one, and FAT or exFAT."""
        is_trusted = self._trust_by_device.get(info.st_dev)
        if is_trusted is None:
            is_trusted = self._trust_by_device[info.st_dev] = self._resolve_trust(path, info.st_dev)
        return is_trusted

    def _resolve_trust(self, path: str, device: int) -> bool:
        if sys.platform == "win32":
            return _is_trusted_windows_volume(path)
        if sys.platform != "linux":
            return True
        if self._linux_types is None:
            self._linux_types = _fetch_linux_types()
        fs_type = self._linux_types.get(device)
        return fs_type is None or not _is_untrusted_linux_type(fs_type)


if sys.platform == "linux":

    def _is_untrusted_linux_type(fs_type: str) -> bool:
        return fs_type in _UNTRUSTED_LINUX_TYPES or fs_type == "fuse" or fs_type.startswith("fuse.")

    def _fetch_linux_types() -> dict[int, str]:
        """Return the type of each mounted file system by its device number, as `st_dev` holds it, or none where the mount table can't be read."""
        try:
            text = _read_mountinfo()
        except OSError:
            return {}
        types = {}
        for line in text.splitlines():
            fields = line.split()
            if _MOUNTINFO_FIELDS_SEPARATOR not in fields[6:]:
                continue
            major, _, minor = fields[2].partition(":")
            fs_type = fields[fields.index(_MOUNTINFO_FIELDS_SEPARATOR, 6) + 1]
            types[os.makedev(int(major), int(minor))] = fs_type
        return types

    def _read_mountinfo() -> str:
        with open(_MOUNTINFO, encoding="utf-8", errors="surrogateescape") as file:
            return file.read()


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.GetVolumePathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    _kernel32.GetVolumePathNameW.restype = wintypes.BOOL
    _kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetDriveTypeW.restype = wintypes.UINT
    _kernel32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.LPDWORD,
        wintypes.LPDWORD,
        wintypes.LPDWORD,
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    _kernel32.GetVolumeInformationW.restype = wintypes.BOOL

    _FILE_READ_ATTRIBUTES = 0x80
    _FILE_SHARE_ALL = 0x7
    _OPEN_EXISTING = 3
    # Needed to open a directory, and harmless for a file.
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_BASIC_INFO_CLASS = 0
    _DRIVE_REMOTE = 4
    _INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
    _PATH_CHARS = 32768
    _FS_NAME_CHARS = 261
    # FILETIME counts 100 ns intervals since 1601-01-01, and Python's times count ns since 1970-01-01.
    _FILETIME_TO_UNIX_100NS = 116444736000000000
    _NS_PER_100NS = 100

    class _FileBasicInfo(ctypes.Structure):
        _fields_ = (
            ("creation_time", ctypes.c_int64),
            ("last_access_time", ctypes.c_int64),
            ("last_write_time", ctypes.c_int64),
            ("change_time", ctypes.c_int64),
            ("file_attributes", wintypes.DWORD),
        )

    def read_change_time_ns(path: str) -> int:
        """Return when the file at `path` last changed, content or metadata, which `os.stat` leaves out on Windows, raising OSError where it can't be read."""
        handle = _kernel32.CreateFileW(
            path,
            _FILE_READ_ATTRIBUTES,
            _FILE_SHARE_ALL,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            info = _FileBasicInfo()
            is_read = _kernel32.GetFileInformationByHandleEx(
                handle, _FILE_BASIC_INFO_CLASS, ctypes.byref(info), ctypes.sizeof(info)
            )
            if not is_read:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _kernel32.CloseHandle(handle)
        return int(info.change_time - _FILETIME_TO_UNIX_100NS) * _NS_PER_100NS

    def _is_trusted_windows_volume(path: str) -> bool:
        """Say whether the volume holding `path`, links resolved, is a local one other than FAT or exFAT. A network share counts as remote whatever file system its server reports."""
        volume = ctypes.create_unicode_buffer(_PATH_CHARS)
        if not _kernel32.GetVolumePathNameW(os.path.realpath(path), volume, _PATH_CHARS):
            return False
        if _kernel32.GetDriveTypeW(volume.value) == _DRIVE_REMOTE:
            return False
        name = ctypes.create_unicode_buffer(_FS_NAME_CHARS)
        is_read = _kernel32.GetVolumeInformationW(
            volume.value, None, 0, None, None, None, name, _FS_NAME_CHARS
        )
        return bool(is_read) and name.value.upper() not in _UNTRUSTED_WINDOWS_NAMES

"""The default job count: every CPU the process may use, capped by a container's CPU quota."""

import math
import os
import posixpath

_CGROUP_MOUNT = "/sys/fs/cgroup"
_CGROUP_MEMBERSHIP = "/proc/self/cgroup"
_V2_PREFIX = "0::"
_NO_QUOTA = "max"


def calc_default_jobs() -> int:
    """Return how many recipes may execute at once by default: the CPUs in the process's affinity set, or else the machine's, and no more than its cgroup's CPU quota rounded up."""
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    quota = find_cpu_quota(_CGROUP_MEMBERSHIP, _CGROUP_MOUNT)
    if quota is None:
        return cpus or 1
    return max(1, min(cpus or 1, math.ceil(quota)))


def find_cpu_quota(membership_file: str, mount: str) -> float | None:
    """Return the fewest CPUs the cgroup v2 quotas allow the cgroup that `membership_file` names, under the hierarchy mounted at `mount`, or failing those the cgroup v1 quota at the mount's root. None where no quota is set or readable, as on any OS but Linux."""
    try:
        with open(membership_file, encoding="utf-8") as file:
            lines = file.read().splitlines()
    except OSError:
        return None
    quotas = []
    for line in lines:
        if not line.startswith(_V2_PREFIX):
            continue
        group = posixpath.normpath(posixpath.join(mount, line[len(_V2_PREFIX) :].lstrip("/")))
        while group.startswith(mount):
            quotas.append(_read_v2_quota(posixpath.join(group, "cpu.max")))
            group = posixpath.dirname(group)
    quotas.append(_read_v1_quota(posixpath.join(mount, "cpu")))
    known = [quota for quota in quotas if quota is not None]
    return min(known) if known else None


def _read_v2_quota(path: str) -> float | None:
    fields = _read_fields(path)
    if len(fields) != 2 or fields[0] == _NO_QUOTA:
        return None
    return _divide(fields[0], fields[1])


def _read_v1_quota(directory: str) -> float | None:
    quota = _read_fields(posixpath.join(directory, "cpu.cfs_quota_us"))
    period = _read_fields(posixpath.join(directory, "cpu.cfs_period_us"))
    if len(quota) != 1 or len(period) != 1:
        return None
    return _divide(quota[0], period[0])


def _read_fields(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as file:
            return file.read().split()
    except OSError:
        return []


def _divide(quota: str, period: str) -> float | None:
    """Return `quota` over `period`, or None where either is no positive number, as cgroup v1 writes -1 for no quota."""
    try:
        cpus = int(quota) / int(period)
    except (ValueError, ZeroDivisionError):
        return None
    return cpus if cpus > 0 else None

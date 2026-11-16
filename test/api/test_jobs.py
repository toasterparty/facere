"""The default job count: the CPUs the process may use, no more than a container's CPU quota allows."""

from pathlib import Path

from facere._jobs import find_cpu_quota


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_cgroup_v2_quota_of_the_process_cgroup_or_an_ancestor_caps_the_jobs(tmp_path: Path) -> None:
    _write(tmp_path / "proc", "0::/ci/job\n")
    _write(tmp_path / "cgroup" / "ci" / "job" / "cpu.max", "max 100000\n")
    _write(tmp_path / "cgroup" / "ci" / "cpu.max", "250000 100000\n")

    assert find_cpu_quota(str(tmp_path / "proc"), str(tmp_path / "cgroup")) == 2.5


def test_cgroup_v1_quota_caps_the_jobs(tmp_path: Path) -> None:
    _write(tmp_path / "proc", "4:cpu,cpuacct:/\n")
    _write(tmp_path / "cgroup" / "cpu" / "cpu.cfs_quota_us", "200000\n")
    _write(tmp_path / "cgroup" / "cpu" / "cpu.cfs_period_us", "100000\n")

    assert find_cpu_quota(str(tmp_path / "proc"), str(tmp_path / "cgroup")) == 2.0


def test_no_quota_leaves_the_jobs_uncapped(tmp_path: Path) -> None:
    _write(tmp_path / "proc", "0::/\n")
    _write(tmp_path / "cgroup" / "cpu.max", "max 100000\n")
    _write(tmp_path / "cgroup" / "cpu" / "cpu.cfs_quota_us", "-1\n")
    _write(tmp_path / "cgroup" / "cpu" / "cpu.cfs_period_us", "100000\n")

    assert find_cpu_quota(str(tmp_path / "proc"), str(tmp_path / "cgroup")) is None


def test_no_cgroup_file_leaves_the_jobs_uncapped(tmp_path: Path) -> None:
    assert find_cpu_quota(str(tmp_path / "missing"), str(tmp_path)) is None

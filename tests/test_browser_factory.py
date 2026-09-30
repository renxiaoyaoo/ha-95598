import os
from pathlib import Path

from scripts.support.browser_factory import prune_profile_cache


def test_profile_cache_pruning_removes_oldest_files_first(tmp_path: Path):
    cache_dir = tmp_path / "Default" / "Code Cache"
    cache_dir.mkdir(parents=True)
    files = [cache_dir / f"cache-{index}" for index in range(3)]
    for index, path in enumerate(files):
        path.write_bytes(b"x" * 10)
        os.utime(path, (index + 1, index + 1))

    removed_files, removed_bytes = prune_profile_cache(tmp_path, limit_bytes=15)

    assert removed_files == 2
    assert removed_bytes == 20
    assert not files[0].exists()
    assert not files[1].exists()
    assert files[2].exists()


def test_profile_cache_pruning_can_be_disabled(tmp_path: Path):
    cache_file = tmp_path / "Default" / "Cache" / "cache-entry"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"x" * 10)

    assert prune_profile_cache(tmp_path, limit_bytes=0) == (0, 0)
    assert cache_file.exists()

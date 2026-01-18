"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator, Optional

import pytest


def run_or_skip(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command or skip the test with the command error output."""
    kwargs.setdefault("check", True)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    try:
        return subprocess.run(cmd, **kwargs)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        stdout = exc.stdout or ""
        details = stderr.strip() or stdout.strip() or f"exit status {exc.returncode}"
        pytest.skip(f"Command failed: {' '.join(cmd)}: {details}")

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config_file(temp_dir: Path) -> Path:
    """Create a test configuration file."""
    config_content = """
enforce_on_usb_only = true
allow_luks1_readonly = true
default_plain_mount_opts = ["nodev", "nosuid", "noexec", "ro"]
default_encrypted_mount_opts = ["nodev", "nosuid", "rw"]
require_noexec_on_plain = true
min_passphrase_length = 12
encryption_target_mode = "whole_disk"
filesystem_type = "exfat"
notification_enabled = true
exempted_groups = ["usb-exempt"]

[kdf]
type = "argon2id"

[cipher]
type = "aes-xts-plain64"
key_size = 512
"""
    config_path = temp_dir / "config.toml"
    config_path.write_text(config_content)
    return config_path


@pytest.fixture
def mock_empty_config(temp_dir: Path) -> Path:
    """Create an empty configuration file."""
    config_path = temp_dir / "empty_config.toml"
    config_path.write_text("")
    return config_path


def is_root() -> bool:
    """Check if running as root."""
    return os.geteuid() == 0


def has_command(cmd: str) -> bool:
    """Check if a command is available."""
    return shutil.which(cmd) is not None


@pytest.fixture
def require_root():
    """Skip test if not running as root."""
    if not is_root():
        pytest.skip("This test requires root privileges")


@pytest.fixture
def require_cryptsetup():
    """Skip test if cryptsetup is not available."""
    if not has_command("cryptsetup"):
        pytest.skip("This test requires cryptsetup")


@pytest.fixture
def require_veracrypt():
    """Skip test if veracrypt is not available."""
    if not has_command("veracrypt"):
        pytest.skip("This test requires veracrypt (install from https://www.veracrypt.fr)")


@pytest.fixture
def require_losetup():
    """Skip test if losetup is not available."""
    if not has_command("losetup"):
        pytest.skip("This test requires losetup")


class LoopDevice:
    """Context manager for loop devices."""
    
    def __init__(self, size_mb: int = 100):
        self.size_mb = size_mb
        self.image_file: Optional[Path] = None
        self.loop_device: Optional[str] = None
        self.temp_dir: Optional[Path] = None
    
    def __enter__(self) -> str:
        """Create and setup loop device."""
        if not is_root():
            raise RuntimeError("Loop device creation requires root")
        
        # Create temporary directory and image file
        self.temp_dir = Path(tempfile.mkdtemp(prefix="usb-enforcer-test-"))
        self.image_file = self.temp_dir / "disk.img"
        
        # Create sparse file
        with open(self.image_file, 'wb') as f:
            f.seek(self.size_mb * 1024 * 1024 - 1)
            f.write(b'\0')
        
        # Setup loop device
        result = subprocess.run(
            ["losetup", "-f", "--show", str(self.image_file)],
            capture_output=True,
            text=True,
            check=True
        )
        self.loop_device = result.stdout.strip()
        return self.loop_device
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup loop device."""
        if self.loop_device:
            try:
                subprocess.run(["losetup", "-d", self.loop_device], check=False)
            except Exception:
                pass
        
        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass


@pytest.fixture
def loop_device(require_root, require_losetup) -> Generator[LoopDevice, None, None]:
    """Provide a loop device context manager."""
    yield LoopDevice


@pytest.fixture
def simple_loop_device(require_root, require_losetup) -> Generator[str, None, None]:
    """Create a simple loop device for testing."""
    with LoopDevice(size_mb=100) as device:
        yield device


# Mock device properties for unit testing
@pytest.fixture
def mock_usb_partition_device() -> dict:
    """Mock USB partition device properties."""
    return {
        "ID_BUS": "usb",
        "ID_TYPE": "partition",
        "DEVTYPE": "partition",
        "DEVNAME": "/dev/sdb1",
        "ID_FS_TYPE": "ext4",
        "ID_FS_UUID": "test-uuid-1234",
    }


@pytest.fixture
def mock_usb_disk_device() -> dict:
    """Mock USB disk device properties."""
    return {
        "ID_BUS": "usb",
        "ID_TYPE": "disk",
        "DEVTYPE": "disk",
        "DEVNAME": "/dev/sdb",
    }


@pytest.fixture
def mock_luks2_device() -> dict:
    """Mock LUKS2 encrypted device properties."""
    return {
        "ID_BUS": "usb",
        "ID_TYPE": "partition",
        "DEVTYPE": "partition",
        "DEVNAME": "/dev/sdb1",
        "ID_FS_TYPE": "crypto_LUKS",
        "ID_FS_VERSION": "2",
    }


@pytest.fixture
def mock_luks1_device() -> dict:
    """Mock LUKS1 encrypted device properties."""
    return {
        "ID_BUS": "usb",
        "ID_TYPE": "partition",
        "DEVTYPE": "partition",
        "DEVNAME": "/dev/sdb1",
        "ID_FS_TYPE": "crypto_LUKS",
        "ID_FS_VERSION": "1",
    }


@pytest.fixture
def mock_mapper_device() -> dict:
    """Mock device mapper (unlocked LUKS) device properties."""
    return {
        "DM_UUID": "CRYPT-LUKS2-test-uuid",
        "DM_NAME": "luks-test-device",
        "DEVNAME": "/dev/mapper/luks-test-device",
        "ID_FS_TYPE": "ext4",
    }


@pytest.fixture
def mock_non_usb_device() -> dict:
    """Mock non-USB device properties."""
    return {
        "ID_BUS": "ata",
        "ID_TYPE": "disk",
        "DEVTYPE": "disk",
        "DEVNAME": "/dev/sda",
    }

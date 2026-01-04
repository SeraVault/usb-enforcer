from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Optional


class CryptoError(Exception):
    pass


def _run(cmd: List[str], input_data: Optional[bytes] = None):
    try:
        result = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            check=True,
        )
        return result
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode().strip() if exc.stderr else ""
        raise CryptoError(f"{' '.join(cmd)} failed: {stderr}") from exc


def luks_version(devnode: str) -> Optional[str]:
    try:
        out = _run(["cryptsetup", "luksDump", devnode]).stdout.decode().strip()
    except CryptoError:
        return None
    for line in out.splitlines():
        if line.strip().startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return None


def unlock_luks(devnode: str, mapper_name: str, passphrase: str) -> str:
    cmd = ["cryptsetup", "open", devnode, mapper_name]
    _run(cmd, input_data=passphrase.encode())
    return f"/dev/mapper/{mapper_name}"


def close_mapper(mapper_name: str) -> None:
    _run(["cryptsetup", "close", mapper_name])


def create_filesystem(devnode: str, fs_type: str = "ext4", label: Optional[str] = None, uid: Optional[int] = None, gid: Optional[int] = None) -> None:
    if fs_type == "ext4":
        cmd = ["mkfs.ext4", "-F"]
        if label:
            cmd += ["-L", label]
        # Set root directory ownership at filesystem creation time
        if uid is not None and gid is not None:
            cmd += ["-E", f"root_owner={uid}:{gid}"]
        cmd.append(devnode)
    elif fs_type == "exfat":
        cmd = ["mkfs.exfat"]
        if label:
            cmd += ["-n", label]
        cmd.append(devnode)
    else:
        raise CryptoError(f"Unsupported filesystem: {fs_type}")
    _run(cmd)


def mount_device(devnode: str, mountpoint: str, options: List[str], uid: Optional[int] = None, gid: Optional[int] = None) -> None:
    os.makedirs(mountpoint, exist_ok=True)
    opt_str = ",".join(options)
    _run(["mount", "-o", opt_str, devnode, mountpoint])
    # Set ownership for user access - chown the mounted filesystem root, not just the mountpoint
    if uid is not None and gid is not None:
        try:
            os.chown(mountpoint, uid, gid)
            # Also create a lost+found if it doesn't exist and change any root-owned directories
            for root, dirs, files in os.walk(mountpoint):
                os.chown(root, uid, gid)
                for d in dirs:
                    os.chown(os.path.join(root, d), uid, gid)
                for f in files:
                    os.chown(os.path.join(root, f), uid, gid)
                break  # Only process top level
        except Exception:
            pass  # Continue even if chown fails


def encrypt_device(
    devnode: str,
    mapper_name: str,
    passphrase: str,
    fs_type: str,
    mount_opts: List[str],
    label: Optional[str] = None,
    progress_cb: Optional[Callable[[str, int], None]] = None,
    kdf_opts: Optional[dict] = None,
    cipher_opts: Optional[dict] = None,
    uid: Optional[int] = None,
    gid: Optional[int] = None,
    username: Optional[str] = None,
) -> str:
    def emit(stage: str, pct: int):
        if progress_cb:
            progress_cb(stage, pct)

    # Unmount the device if it's currently mounted
    emit("unmount", 5)
    
    # Try udisksctl first (better for user-mounted devices)
    try:
        _run(["udisksctl", "unmount", "-b", devnode])
    except (CryptoError, FileNotFoundError):
        pass  # Try regular umount next
    
    # Force unmount the device
    try:
        _run(["umount", "-f", devnode])
    except CryptoError:
        pass  # Device wasn't mounted, continue
    
    # If this is a whole disk, unmount all its partitions
    try:
        # Get list of partitions and unmount them
        result = _run(["lsblk", "-n", "-o", "NAME", devnode])
        lines = result.stdout.strip().split(b'\n') if result.stdout else []
        for line in lines[1:]:  # Skip first line (parent device)
            partition = line.decode().strip().replace('└─', '').replace('├─', '').replace('│', '').strip()
            if partition:
                part_dev = f"/dev/{partition}"
                # Try udisksctl first
                try:
                    _run(["udisksctl", "unmount", "-b", part_dev])
                except (CryptoError, FileNotFoundError):
                    pass
                # Then force unmount
                try:
                    _run(["umount", "-f", part_dev])
                except CryptoError:
                    pass  # Continue if partition not mounted
    except (CryptoError, Exception):
        pass  # Continue anyway

    # Set device to read-write mode before wiping
    emit("prepare", 7)
    try:
        _run(["blockdev", "--setrw", devnode])
    except CryptoError:
        pass  # Continue even if this fails

    # Wipe partition table and filesystem signatures
    emit("wipe", 8)
    
    # For whole disks, delete all partitions first
    try:
        # List partitions using parted
        result = _run(["parted", "-s", devnode, "print"])
        # Delete all partitions by creating a fresh partition table
        _run(["parted", "-s", devnode, "mklabel", "gpt"])
    except (CryptoError, FileNotFoundError):
        pass  # Continue anyway
    
    try:
        # Wipe all filesystem signatures
        _run(["wipefs", "--all", "--force", devnode])
    except CryptoError:
        pass  # Continue even if wipefs fails

    # Zero out the first 10MB to ensure clean slate
    try:
        _run(["dd", "if=/dev/zero", f"of={devnode}", "bs=1M", "count=10", "conv=fsync"])
    except CryptoError:
        pass  # Continue even if dd fails

    # Sync and inform kernel
    try:
        _run(["sync"])
        _run(["partprobe", devnode])
    except (CryptoError, FileNotFoundError):
        pass

    emit("luks_format", 10)
    pbkdf_type = (kdf_opts or {}).get("type", "argon2id")
    cipher_type = (cipher_opts or {}).get("type", "aes-xts-plain64")
    key_size = str((cipher_opts or {}).get("key_size", 512))

    # Ensure device is RW right before formatting (udev monitor may have set it RO again)
    try:
        _run(["blockdev", "--setrw", devnode])
    except CryptoError:
        pass

    luks_format_cmd = [
        "cryptsetup",
        "luksFormat",
        "--batch-mode",  # Don't ask for confirmation
        "--type",
        "luks2",
        "--hash",
        "sha256",
        "--pbkdf",
        pbkdf_type,
        "--cipher",
        cipher_type,
        "--key-size",
        key_size,
        devnode,
    ]
    mapper = None
    try:
        _run(luks_format_cmd, input_data=passphrase.encode())
        emit("unlock", 40)
        mapper = unlock_luks(devnode, mapper_name, passphrase)
        emit("mkfs", 60)
        create_filesystem(mapper, fs_type=fs_type, label=label, uid=uid, gid=gid)
        emit("done", 100)
        # Return mapper path - let system automount handle mounting
        return f"/dev/mapper/{mapper_name}"
    except Exception:
        if mapper:
            try:
                close_mapper(mapper_name)
            except Exception:
                pass
        raise

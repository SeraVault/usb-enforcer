from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

try:
    import pyudev
except ImportError:
    pyudev = None

try:
    import pydbus
except ImportError:
    pydbus = None


class CryptoError(Exception):
    pass


def _udisks2_unmount(devnode: str) -> bool:
    """Unmount a device using UDisks2 D-Bus API. Returns True if successful."""
    if not pydbus:
        return False
    
    try:
        bus = pydbus.SystemBus()
        udisks = bus.get("org.freedesktop.UDisks2")
        
        # Get the block device object path from device node
        # UDisks2 uses object paths like /org/freedesktop/UDisks2/block_devices/sda1
        dev_name = devnode.replace("/dev/", "").replace("/", "_")
        obj_path = f"/org/freedesktop/UDisks2/block_devices/{dev_name}"
        
        try:
            filesystem = bus.get("org.freedesktop.UDisks2", obj_path)
            # Call Unmount with empty options dict
            filesystem.Unmount({})
            return True
        except Exception:
            # Device might not have filesystem interface or not mounted
            return False
    except Exception:
        return False


def _get_mounted_devices() -> dict:
    """Read /proc/mounts and return a dict of device -> mountpoint."""
    mounted = {}
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0].startswith("/dev/"):
                    mounted[parts[0]] = parts[1]
    except Exception:
        pass
    return mounted


def _get_device_partitions(devnode: str) -> List[str]:
    """Get list of partition device nodes for a given disk device using pyudev."""
    partitions = []
    
    if pyudev:
        try:
            context = pyudev.Context()
            device = pyudev.Devices.from_device_file(context, devnode)
            
            # Enumerate child devices (partitions)
            for child in context.list_devices(parent=device):
                if child.device_type == 'partition' and child.device_node:
                    partitions.append(child.device_node)
        except Exception:
            pass  # Fall back to checking if it's a partition itself
    
    # If devnode itself is a partition, include it
    if devnode and devnode[-1].isdigit():
        if devnode not in partitions:
            partitions.append(devnode)
    
    return partitions


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
    
    # Get all partitions for this device using pyudev
    partitions = _get_device_partitions(devnode)
    mounted_devices = _get_mounted_devices()
    
    # Unmount all related devices (partitions first, then parent)
    devices_to_unmount = partitions + [devnode]
    for dev in devices_to_unmount:
        if dev in mounted_devices:
            # Try UDisks2 D-Bus API first (cleanest)
            if _udisks2_unmount(dev):
                continue
            
            # Fall back to udisksctl command
            try:
                _run(["udisksctl", "unmount", "-b", dev])
            except (CryptoError, FileNotFoundError):
                pass
            
            # Finally try force unmount with lazy flag
            try:
                _run(["umount", "-f", "-l", dev])
            except CryptoError:
                pass
            # Then force unmount with lazy flag
            try:
                _run(["umount", "-f", "-l", dev])
            except CryptoError:
                pass

    # Set device and all partitions to read-write mode before wiping
    emit("prepare", 7)
    for dev in devices_to_unmount:
        try:
            _run(["blockdev", "--setrw", dev])
        except CryptoError:
            pass

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
        
        # Mount the encrypted device automatically (daemon runs as root, no auth needed)
        emit("mount", 80)
        mapper_path = f"/dev/mapper/{mapper_name}"
        
        # Give udev a moment to process the new device
        import time
        time.sleep(1)
        
        # Use direct mount command (daemon has root privileges, bypasses PolicyKit)
        mounted = False
        mountpoint = None
        
        if username:
            mountpoint = f"/media/{username}/{mapper_name}"
        else:
            mountpoint = f"/mnt/{mapper_name}"
        
        mount_opts = ["rw"]
        if uid is not None and gid is not None:
            mount_opts.extend([f"uid={uid}", f"gid={gid}"])
        
        try:
            mount_device(mapper_path, mountpoint, mount_opts, uid, gid)
            mounted = True
            print(f"Auto-mounted {mapper_path} at {mountpoint}")
        except Exception as e:
            # If mount fails, still return the mapper - user can mount manually
            print(f"Auto-mount failed: {e}")
            pass
        
        emit("done", 100)
        # Return mountpoint if mounted, otherwise mapper path
        return mountpoint if mounted and mountpoint else mapper_path
    except Exception:
        if mapper:
            try:
                close_mapper(mapper_name)
            except Exception:
                pass
        raise

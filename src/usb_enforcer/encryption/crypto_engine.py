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


def veracrypt_version(devnode: str) -> Optional[str]:
    """Check if device is VeraCrypt encrypted and return version info.
    
    VeraCrypt volumes have encrypted headers with no magic number, making
    detection challenging. This function uses heuristics:
    1. Check if device is currently mounted as VeraCrypt
    2. Conservatively check for encrypted header (exclude known formats)
    """
    try:
        # Check if veracrypt command is available
        import shutil
        if not shutil.which("veracrypt"):
            return None
        
        # First, check if volume is currently mounted
        result = subprocess.run(
            ["veracrypt", "--text", "--list"],
            capture_output=True,
            check=False,
            timeout=2
        )
        
        if result.returncode == 0:
            output = result.stdout.decode()
            # Check if our device is in the mounted list
            if devnode in output:
                return "veracrypt"
        
        # For unmounted volumes, check header characteristics
        # Be CONSERVATIVE - only detect as VeraCrypt if we're very confident
        try:
            with open(devnode, 'rb') as f:
                header = f.read(4096)  # Read more data for better analysis
                
            if len(header) < 512:
                return None
                
            # Check for known non-VeraCrypt signatures first
            # LUKS has "LUKS" magic at offset 0
            if header[:4] == b'LUKS' or header[:6] == b'LUKS\xba\xbe':
                return None
            
            # Check for common filesystem signatures
            # ext2/3/4 has 0x53EF at offset 0x438 (1080)
            if len(header) >= 1082:
                if header[1080:1082] == b'\x53\xEF':
                    return None
                # Also check little-endian
                if header[1080:1082] == b'\xEF\x53':
                    return None
            
            # FAT has specific boot signature
            if len(header) >= 512:
                if header[510:512] == b'\x55\xAA':
                    # Check for FAT signatures
                    if b'FAT12' in header[:512] or b'FAT16' in header[:512] or b'FAT32' in header[:512]:
                        return None
                    # Check for other boot sector patterns
                    if b'NTFS' in header[:512] or b'EXFAT' in header[:512]:
                        return None
            
            # If first 512 bytes are all zeros, definitely not VeraCrypt
            if header[:512] == b'\x00' * 512:
                return None
            
            # Check if it looks like a typical filesystem superblock
            # Most filesystems have readable strings or patterns
            # VeraCrypt headers are completely random-looking but may have some structure
            printable_count = sum(1 for b in header[:512] if 32 <= b < 127)
            if printable_count > 250:  # Relaxed threshold - encrypted data can have printable bytes
                return None
            
            # Check for very low entropy (indicates not encrypted)
            unique_bytes = len(set(header[:512]))
            if unique_bytes < 180:  # Relaxed threshold - VeraCrypt may have some structure
                return None
            
            # Additional check: VeraCrypt volumes should have uniform byte distribution
            # Calculate standard deviation of byte frequencies
            byte_counts = [0] * 256
            for b in header[:512]:
                byte_counts[b] += 1
            
            # If any byte appears too frequently, it's probably not encrypted
            max_count = max(byte_counts)
            if max_count > 10:  # Any single byte appears more than 10 times in 512 bytes
                return None
            
            # At this point, it looks like encrypted data
            # Return "veracrypt" tentatively
            # Real verification happens during unlock attempt
            return "veracrypt"
            
        except (IOError, OSError, PermissionError):
            return None
        
    except (subprocess.TimeoutExpired, Exception):
        return None


def unlock_luks(devnode: str, mapper_name: str, passphrase: str) -> str:
    cmd = ["cryptsetup", "open", devnode, mapper_name]
    _run(cmd, input_data=passphrase.encode())
    return f"/dev/mapper/{mapper_name}"


def unlock_veracrypt(devnode: str, mapper_name: str, passphrase: str, username: Optional[str] = None, uid: Optional[int] = None, gid: Optional[int] = None) -> str:
    """Unlock a VeraCrypt encrypted device."""
    # VeraCrypt mounts volumes directly, not via /dev/mapper
    # Mount under /media/$USER/ for proper file browser integration
    # Get the actual user (not root when running via sudo)
    if not username:
        username = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'root'
    
    # Get UID/GID if not provided
    if uid is None:
        try:
            import pwd
            pw = pwd.getpwnam(username)
            uid = pw.pw_uid
            gid = pw.pw_gid
        except (KeyError, ImportError):
            uid = 0
            gid = 0
    
    mount_point = f"/media/{username}/{mapper_name}"
    
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(mount_point), exist_ok=True)
    
    # Create mount point directory if it doesn't exist
    if not os.path.exists(mount_point):
        os.makedirs(mount_point, exist_ok=True)
    
    # Build mount options to set ownership
    # For exfat: uid,gid,fmask,dmask
    fs_options = f"uid={uid},gid={gid},fmask=0022,dmask=0022"
    
    cmd = [
        "veracrypt",
        "--text",
        "--non-interactive",
        "--stdin",  # Read password from stdin
        "--filesystem=exfat",  # Specify filesystem type
        "--fs-options", fs_options,  # Set ownership and permissions
        devnode,
        mount_point
    ]
    _run(cmd, input_data=passphrase.encode())
    
    # VeraCrypt creates a virtual device mapper, find it
    # The actual device will be like /dev/mapper/veracrypt1
    import time
    time.sleep(0.5)  # Give VeraCrypt time to create the mapper
    
    # List /dev/mapper to find the VeraCrypt device
    try:
        import glob
        mappers = glob.glob("/dev/mapper/veracrypt*")
        if mappers:
            # Return the most recently created one
            return sorted(mappers, key=lambda x: os.path.getmtime(x))[-1]
    except Exception:
        pass
    
    # Fallback: return mount point (filesystem operations will use this)
    return mount_point


def close_mapper(mapper_name: str, encryption_type: str = "luks") -> None:
    """Close an encrypted mapper device (LUKS or VeraCrypt)."""
    if encryption_type == "veracrypt":
        # For VeraCrypt, mapper_name might be a mount point or device
        # Try to dismount by device/mount point
        try:
            _run(["veracrypt", "--text", "--dismount", mapper_name])
        except CryptoError:
            # Try with /media prefix if it's just a name
            try:
                _run(["veracrypt", "--text", "--dismount", f"/media/veracrypt-{mapper_name}"])
            except CryptoError:
                pass  # Already dismounted or not found
    else:
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
    encryption_type: str = "luks2",
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
    
    # Determine encryption format
    is_veracrypt = encryption_type.lower() == "veracrypt"
    
    if is_veracrypt:
        # VeraCrypt encryption
        emit("veracrypt_format", 10)
        
        # Check if veracrypt is installed
        import shutil
        if not shutil.which("veracrypt"):
            raise CryptoError("VeraCrypt is not installed. Install from https://www.veracrypt.fr or use LUKS2 encryption instead.")
        
        # Ensure device is RW right before formatting
        try:
            _run(["blockdev", "--setrw", devnode])
        except CryptoError:
            pass
        
        # Create VeraCrypt volume
        # VeraCrypt uses --create to format a volume
        # Note: --size is not used for device-hosted volumes (uses entire device automatically)
        # Pass password via stdin with --stdin flag for better compatibility
        # Use --quick to skip encrypting empty space (much faster, equivalent to LUKS behavior)
        veracrypt_cmd = [
            "veracrypt",
            "--text",
            "--create",
            devnode,
            "--volume-type=normal",
            "--encryption=AES",
            "--hash=SHA-512",
            "--filesystem=none",  # We'll create filesystem after
            "--quick",  # Skip encrypting empty space
            "--stdin",  # Read password from stdin
            "--pim=0",  # Use default PIM
            "--keyfiles=",
            "--random-source=/dev/urandom",
            "--non-interactive"
        ]
        
        mapper = None
        mapper_device = None
        try:
            # Pass password via stdin (needs to be provided twice for creation)
            password_input = f"{passphrase}\n{passphrase}\n".encode()
            _run(veracrypt_cmd, input_data=password_input)
            
            emit("unlock", 40)
            # After creation with --filesystem=none, we need to unlock without mounting
            # to get the mapper device, then format it
            # Use --mount-options=headerbak to unlock without filesystem check
            unlock_cmd = [
                "veracrypt",
                "--text",
                "--non-interactive",
                "--stdin",
                "--filesystem=none",  # Don't try to mount filesystem yet
                devnode
            ]
            _run(unlock_cmd, input_data=passphrase.encode())
            
            # Find the actual /dev/mapper device that VeraCrypt created
            import glob
            import time
            time.sleep(0.5)  # Give system time to create mapper
            veracrypt_mappers = glob.glob("/dev/mapper/veracrypt*")
            if veracrypt_mappers:
                # Get the most recently created one
                mapper_device = sorted(veracrypt_mappers, key=lambda x: os.path.getmtime(x))[-1]
            else:
                raise CryptoError("Could not find VeraCrypt mapper device")
            
            emit("mkfs", 60)
            # Format the mapper device (this is running as root, so it has permissions)
            create_filesystem(mapper_device, fs_type=fs_type, label=label, uid=uid, gid=gid)
            
            # Dismount the VeraCrypt volume (this also removes the mapper)
            try:
                _run(["veracrypt", "--text", "--dismount", devnode])
            except CryptoError:
                pass
            
            emit("remount", 80)
            # Re-unlock without mounting so udisks2 can auto-mount with proper user permissions
            unlock_cmd = [
                "veracrypt",
                "--text",
                "--non-interactive",
                "--stdin",
                "--filesystem=none",  # Don't mount, just create mapper
                devnode
            ]
            _run(unlock_cmd, input_data=passphrase.encode())
            
            # Wait for mapper to be created
            time.sleep(0.5)
            veracrypt_mappers = glob.glob("/dev/mapper/veracrypt*")
            if veracrypt_mappers:
                mapper_device = sorted(veracrypt_mappers, key=lambda x: os.path.getmtime(x))[-1]
            
            # Trigger udev to detect the mapper device and let udisks2 auto-mount it
            try:
                _run(["udevadm", "trigger", "--action=add", f"--name-match={mapper_device}"])
                _run(["udevadm", "settle"])
            except CryptoError:
                pass
            
            # Let the system automount handle encrypted devices with proper ownership
            emit("done", 100)
            print(f"VeraCrypt encryption complete. Device: {mapper_device}")
            return mapper_device
        except Exception:
            # Try to clean up on error - dismount the device
            try:
                _run(["veracrypt", "--text", "--dismount", devnode])
            except Exception:
                pass
            raise
    else:
        # LUKS encryption (existing code)
        pbkdf_type = (kdf_opts or {}).get("type", "argon2id")
        luks_type = (kdf_opts or {}).get("luks_version") or (kdf_opts or {}).get("luks_type") or "luks2"
        if str(luks_type) in ("1", "luks1"):
            luks_type = "luks1"
        else:
            luks_type = "luks2"
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
            luks_type,
            "--hash",
            "sha256",
        ]
        if luks_type == "luks2":
            luks_format_cmd += ["--pbkdf", pbkdf_type]
        luks_format_cmd += [
            "--cipher",
            cipher_type,
            "--key-size",
            key_size,
            devnode,
        ]
        mapper = None
        try:
            _run(luks_format_cmd, input_data=passphrase.encode())
            
            # Set LUKS2 label if provided
            if label:
                try:
                    _run(["cryptsetup", "config", devnode, "--label", label])
                except CryptoError:
                    pass  # Continue even if label setting fails
            
            emit("unlock", 40)
            mapper = unlock_luks(devnode, mapper_name, passphrase)
            emit("mkfs", 60)
            create_filesystem(mapper, fs_type=fs_type, label=label, uid=uid, gid=gid)
            
            # Let the system automount handle encrypted devices
            # The udev rules have UDISKS_AUTO=1 for mapper devices
            emit("done", 100)
            mapper_path = f"/dev/mapper/{mapper_name}"
            print(f"Encryption complete. Device will be auto-mounted by the system: {mapper_path}")
            return mapper_path
        except Exception:
            if mapper:
                try:
                    close_mapper(mapper_name, "luks")
                except Exception:
                    pass
            raise

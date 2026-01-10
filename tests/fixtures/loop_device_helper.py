#!/usr/bin/env python3
"""Helper script for creating and managing loop devices for testing.

This script simulates USB storage devices using loop devices, allowing
comprehensive testing without physical hardware.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


class LoopDeviceManager:
    """Manage loop devices for testing."""
    
    def __init__(self):
        self.devices = []
        self.temp_files = []
    
    def create_image_file(self, size_mb: int, name: str = "test") -> Path:
        """Create a sparse image file."""
        temp_dir = Path(tempfile.gettempdir()) / "usb-enforcer-tests"
        temp_dir.mkdir(exist_ok=True)
        
        image_file = temp_dir / f"{name}.img"
        
        # Create sparse file
        with open(image_file, 'wb') as f:
            f.seek(size_mb * 1024 * 1024 - 1)
            f.write(b'\0')
        
        self.temp_files.append(image_file)
        print(f"Created image file: {image_file} ({size_mb}MB)")
        return image_file
    
    def setup_loop_device(self, image_file: Path) -> str:
        """Setup a loop device from an image file."""
        result = subprocess.run(
            ["losetup", "-f", "--show", str(image_file)],
            capture_output=True,
            text=True,
            check=True
        )
        device = result.stdout.strip()
        self.devices.append(device)
        print(f"Setup loop device: {device}")
        return device
    
    def create_partition(self, device: str) -> str:
        """Create a single partition on the device."""
        # Create partition table
        subprocess.run(
            ["parted", "-s", device, "mklabel", "msdos"],
            check=True
        )
        
        # Create partition
        subprocess.run(
            ["parted", "-s", device, "mkpart", "primary", "ext4", "1MiB", "100%"],
            check=True
        )
        
        # Re-read partition table
        subprocess.run(["partprobe", device], check=False)
        
        partition = f"{device}p1"
        print(f"Created partition: {partition}")
        return partition
    
    def format_filesystem(self, device: str, fstype: str = "ext4", label: Optional[str] = None):
        """Format a device with a filesystem."""
        cmd = []
        if fstype == "ext4":
            cmd = ["mkfs.ext4", "-F"]
            if label:
                cmd.extend(["-L", label])
            cmd.append(device)
        elif fstype == "exfat":
            cmd = ["mkfs.exfat"]
            if label:
                cmd.extend(["-n", label])
            cmd.append(device)
        elif fstype == "vfat":
            cmd = ["mkfs.vfat", "-F", "32"]
            if label:
                cmd.extend(["-n", label])
            cmd.append(device)
        else:
            raise ValueError(f"Unsupported filesystem type: {fstype}")
        
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"Formatted {device} with {fstype}")
    
    def encrypt_device(self, device: str, passphrase: str, luks_version: int = 2):
        """Encrypt a device with LUKS."""
        luks_format = f"luks{luks_version}"
        
        # LUKS format the device
        subprocess.run(
            ["cryptsetup", "luksFormat", "--type", luks_format, "--batch-mode", device],
            input=passphrase.encode(),
            check=True,
            capture_output=True
        )
        print(f"Encrypted {device} with LUKS{luks_version}")
    
    def open_luks_device(self, device: str, name: str, passphrase: str) -> str:
        """Open a LUKS encrypted device."""
        subprocess.run(
            ["cryptsetup", "open", device, name],
            input=passphrase.encode(),
            check=True,
            capture_output=True
        )
        mapper_device = f"/dev/mapper/{name}"
        print(f"Opened LUKS device: {mapper_device}")
        return mapper_device
    
    def close_luks_device(self, name: str):
        """Close a LUKS encrypted device."""
        subprocess.run(["cryptsetup", "close", name], check=False, capture_output=True)
        print(f"Closed LUKS device: {name}")
    
    def cleanup(self):
        """Cleanup all loop devices and temp files."""
        # Close any open LUKS devices
        for device in self.devices:
            name = device.split('/')[-1]
            self.close_luks_device(name)
        
        # Detach loop devices
        for device in self.devices:
            subprocess.run(["losetup", "-d", device], check=False, capture_output=True)
            print(f"Detached loop device: {device}")
        
        # Remove temp files
        for temp_file in self.temp_files:
            if temp_file.exists():
                temp_file.unlink()
                print(f"Removed temp file: {temp_file}")


def main():
    parser = argparse.ArgumentParser(description="Loop device manager for USB Enforcer testing")
    parser.add_argument("command", choices=["create", "cleanup"], help="Command to execute")
    parser.add_argument("--size", type=int, default=100, help="Size in MB (default: 100)")
    parser.add_argument("--fstype", default="ext4", help="Filesystem type (default: ext4)")
    parser.add_argument("--encrypt", action="store_true", help="Encrypt the device with LUKS2")
    parser.add_argument("--luks-version", type=int, default=2, choices=[1, 2], help="LUKS version")
    parser.add_argument("--passphrase", default="test-password-123", help="LUKS passphrase")
    parser.add_argument("--partition", action="store_true", help="Create partition on device")
    parser.add_argument("--label", help="Filesystem label")
    
    args = parser.parse_args()
    
    manager = LoopDeviceManager()
    
    try:
        if args.command == "create":
            # Create image file
            image_file = manager.create_image_file(args.size, "test-device")
            
            # Setup loop device
            loop_device = manager.setup_loop_device(image_file)
            
            target_device = loop_device
            
            # Create partition if requested
            if args.partition:
                target_device = manager.create_partition(loop_device)
            
            # Encrypt if requested
            if args.encrypt:
                manager.encrypt_device(target_device, args.passphrase, args.luks_version)
                # Optionally open and format
                mapper_name = "test-luks"
                mapper_device = manager.open_luks_device(target_device, mapper_name, args.passphrase)
                manager.format_filesystem(mapper_device, args.fstype, args.label)
                manager.close_luks_device(mapper_name)
            else:
                # Format plaintext
                manager.format_filesystem(target_device, args.fstype, args.label)
            
            print("\n=== Test Device Created Successfully ===")
            print(f"Loop device: {loop_device}")
            if args.partition:
                print(f"Partition: {target_device}")
            print(f"Encrypted: {args.encrypt}")
            print(f"Filesystem: {args.fstype}")
        
        elif args.command == "cleanup":
            manager.cleanup()
    
    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr.decode() if e.stderr else 'N/A'}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

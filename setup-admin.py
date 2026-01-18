"""Setup script for USB Enforcer Admin GUI (standalone package)."""

from setuptools import setup
from pathlib import Path

# Read minimal requirements
requirements_file = Path(__file__).parent / "requirements-admin.txt"
requirements = []
if requirements_file.exists():
    with open(requirements_file) as f:
        requirements = [
            line.strip() for line in f 
            if line.strip() and not line.startswith('#') and not line.startswith('toml')
        ]

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = ""
if readme_file.exists():
    with open(readme_file, encoding='utf-8') as f:
        long_description = f.read()

setup(
    name="usb-enforcer-admin",
    version="1.0.0",
    author="USB Enforcer Team",
    description="USB Enforcer Administration GUI - Configuration Editor",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/seravault/usb-enforcer",
    py_modules=["usb_enforcer.ui.admin"],
    package_dir={"": "src"},
    install_requires=requirements,
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: System :: Systems Administration",
        "Topic :: Security",
    ],
)

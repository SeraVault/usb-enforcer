"""Setup script for USB Enforcer."""

from setuptools import setup, find_packages
from pathlib import Path
import glob

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    with open(requirements_file) as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = ""
if readme_file.exists():
    with open(readme_file, encoding='utf-8') as f:
        long_description = f.read()

# Collect translation files
locale_files = []
for mo_file in glob.glob("locale/*/LC_MESSAGES/*.mo"):
    # Extract locale code (e.g., 'es' from 'locale/es/LC_MESSAGES/usb-enforcer.mo')
    parts = Path(mo_file).parts
    if len(parts) >= 3:
        locale_code = parts[1]
        target_dir = f"share/locale/{locale_code}/LC_MESSAGES"
        locale_files.append((target_dir, [mo_file]))

setup(
    name="usb-enforcer",
    version="1.0.0",
    author="USB Enforcer Team",
    description="USB storage encryption enforcement daemon",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/usb-enforcer",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=requirements,
    python_requires=">=3.10",
    data_files=locale_files,  # Install translation files to /usr/share/locale
    entry_points={
        "console_scripts": [
            "usb-enforcerd=usb_enforcer.daemon:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Systems Administration",
        "Topic :: Security",
    ],
)

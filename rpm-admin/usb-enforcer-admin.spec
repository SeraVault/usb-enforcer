Name:           usb-enforcer-admin
Version:        1.0.0
Release:        1%{?dist}
Summary:        USB Enforcer Administration GUI
License:        GPLv3
URL:            https://github.com/seravault/usb-enforcer
Source0:        usb-enforcer-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools

Requires:       python3 >= 3.8
Requires:       gtk4
Requires:       libadwaita
Requires:       python3-gobject
Requires:       polkit

Recommends:     usb-enforcer

%description
A graphical user interface for configuring USB Enforcer settings.

This administration tool provides an intuitive interface for editing
the config.toml file, with:
 - Visual controls for all configuration options
 - Inline help and validation
 - Direct links to documentation
 - Organized sections for Basic, Security, Encryption, and Scanning settings
 - Real-time validation of configuration values

The admin GUI can be run independently from the main USB Enforcer daemon,
making it suitable for remote administration or configuration on systems
where the enforcement daemon is not running.

%prep
%autosetup -n usb-enforcer-%{version}

%build
# Python package build handled by setup.py
%py3_build

%install
%py3_install

# Create admin directory with dedicated venv
mkdir -p %{buildroot}%{_prefix}/lib/usb-enforcer-admin
python3 -m venv --system-site-packages %{buildroot}%{_prefix}/lib/usb-enforcer-admin/.venv

# Install minimal dependencies in venv
%{buildroot}%{_prefix}/lib/usb-enforcer-admin/.venv/bin/pip install --upgrade pip
# Only install toml if Python < 3.11
%{buildroot}%{_prefix}/lib/usb-enforcer-admin/.venv/bin/python3 -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)' || \
    %{buildroot}%{_prefix}/lib/usb-enforcer-admin/.venv/bin/pip install toml

# Copy admin module
mkdir -p %{buildroot}%{_prefix}/lib/usb-enforcer-admin/usb_enforcer/ui
cp src/usb_enforcer/ui/admin.py %{buildroot}%{_prefix}/lib/usb-enforcer-admin/usb_enforcer/ui/
touch %{buildroot}%{_prefix}/lib/usb-enforcer-admin/usb_enforcer/__init__.py
touch %{buildroot}%{_prefix}/lib/usb-enforcer-admin/usb_enforcer/ui/__init__.py

# Install admin script
install -D -m 755 scripts/usb-enforcer-admin %{buildroot}%{_bindir}/usb-enforcer-admin

# Install desktop file
install -D -m 644 deploy/desktop/usb-enforcer-admin.desktop %{buildroot}%{_datadir}/applications/usb-enforcer-admin.desktop
prefix}/lib/usb-enforcer-admin/
%{_datadir}/applications/usb-enforcer-admin.desktop
%{_datadir}/polkit-1/actions/49-usb-enforcer-admin.policy
%{_datadir}/usb-enforcer/config.toml.sample
%{_docdir}/usb-enforcer/*enforcer/config.toml.sample

# Install documentation
mkdir -p %{buildroot}%{_docdir}/usb-enforcer
cp -r docs/* %{buildroot}%{_docdir}/usb-enforcer/
cp README.md %{buildroot}%{_docdir}/usb-enforcer/

%files
%license LICENSE
%doc README.md
%{_bindir}/usb-enforcer-admin
%{_datadir}/applications/usb-enforcer-admin.desktop
%{_datadir}/polkit-1/actions/49-usb-enforcer-admin.policy
%{_datadir}/usb-enforcer/config.toml.sample
%{_docdir}/usb-enforcer/*
%{python3_sitelib}/usb_enforcer/ui/admin.py
%{python3_sitelib}/usb_enforcer-%{version}-py%{python3_version}.egg-info

%changelog
* Thu Jan 16 2025 Donnie Guedry <dguedry@gmail.com> - 1.0.0-1
- Initial release of USB Enforcer Administration GUI
- Graphical config.toml editor with validation
- Links to documentation for all settings
- Separated from main usb-enforcer package for independent deployment

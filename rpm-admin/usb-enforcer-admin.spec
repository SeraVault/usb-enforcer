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
BuildRequires:  python3-markdown

Requires:       python3 >= 3.8
Requires:       gtk4
Requires:       libadwaita
Requires:       python3-gobject
Requires:       webkit2gtk4.1
Requires:       polkit
# toml module (built-in for Python >= 3.11, separate package for older versions)
Requires:       (python3-toml if python3 < 3.11)

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
# Nothing to build - admin GUI is standalone

%install
# Copy admin module (no venv needed - uses system Python)
mkdir -p %{buildroot}%{_prefix}/lib/usb-enforcer-admin
mkdir -p %{buildroot}%{_prefix}/lib/usb-enforcer-admin/usb_enforcer/ui
cp src/usb_enforcer/ui/admin.py %{buildroot}%{_prefix}/lib/usb-enforcer-admin/usb_enforcer/ui/
cp src/usb_enforcer/i18n.py %{buildroot}%{_prefix}/lib/usb-enforcer-admin/usb_enforcer/
touch %{buildroot}%{_prefix}/lib/usb-enforcer-admin/usb_enforcer/__init__.py
touch %{buildroot}%{_prefix}/lib/usb-enforcer-admin/usb_enforcer/ui/__init__.py

# Install admin script
install -D -m 755 scripts/usb-enforcer-admin %{buildroot}%{_bindir}/usb-enforcer-admin

# Install desktop file
install -D -m 644 deploy/desktop/usb-enforcer-admin.desktop %{buildroot}%{_datadir}/applications/usb-enforcer-admin.desktop

# Install locale files (translations)
for po in locale/*/LC_MESSAGES/*.po; do
    # Check if glob expanded (if not, po will be the pattern itself)
    [ -e "$po" ] || continue
    mo="${po%.po}.mo"
    if [ ! -f "$mo" ] || [ "$po" -nt "$mo" ]; then
        msgfmt "$po" -o "$mo" 2>/dev/null || true
    fi
    if [ -f "$mo" ]; then
        locale_code=$(echo "$po" | cut -d/ -f2)
        install -d "%{buildroot}%{_datadir}/locale/${locale_code}/LC_MESSAGES"
        install -m 0644 "$mo" "%{buildroot}%{_datadir}/locale/${locale_code}/LC_MESSAGES/usb-enforcer.mo"
    fi
done

# Install polkit policy
install -D -m 644 deploy/polkit/49-usb-enforcer-admin.policy %{buildroot}%{_datadir}/polkit-1/actions/49-usb-enforcer-admin.policy

# Install sample config
install -D -m 644 deploy/config.toml.sample %{buildroot}%{_datadir}/usb-enforcer/config.toml.sample

# Install documentation
mkdir -p %{buildroot}%{_docdir}/usb-enforcer
cp -r docs/* %{buildroot}%{_docdir}/usb-enforcer/
cp README.md %{buildroot}%{_docdir}/usb-enforcer/

# Convert markdown to HTML for better display in admin GUI
if command -v python3 >/dev/null 2>&1 && python3 -c "import markdown" 2>/dev/null; then
    mkdir -p %{buildroot}%{_docdir}/usb-enforcer/html
    python3 scripts/convert-docs-to-html.py docs %{buildroot}%{_docdir}/usb-enforcer/html || true
fi

%files
%license LICENSE
%doc README.md
%{_bindir}/usb-enforcer-admin
%{_prefix}/lib/usb-enforcer-admin/
%{_datadir}/applications/usb-enforcer-admin.desktop
%{_datadir}/polkit-1/actions/49-usb-enforcer-admin.policy
%{_datadir}/usb-enforcer/config.toml.sample
%{_docdir}/usb-enforcer/*
%{_datadir}/locale/es/LC_MESSAGES/usb-enforcer.mo
%{_datadir}/locale/fr/LC_MESSAGES/usb-enforcer.mo

%changelog
* Thu Jan 16 2025 Donnie Guedry <dguedry@gmail.com> - 1.0.0-1
- Initial release of USB Enforcer Administration GUI
- Graphical config.toml editor with validation
- Links to documentation for all settings
- Separated from main usb-enforcer package for independent deployment

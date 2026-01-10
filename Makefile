.PHONY: help rpm srpm clean prepare-rpm dist rpm-bundled bundle-deps deb deb-bundled

NAME := usb-encryption-enforcer
NAME_BUNDLED := usb-encryption-enforcer-bundled
VERSION := 1.0.0
RELEASE := 1
TARBALL := $(NAME)-$(VERSION).tar.gz
SPEC_FILE := rpm/$(NAME).spec
SPEC_FILE_BUNDLED := rpm-bundled/$(NAME_BUNDLED).spec
PYTHON_DEPS := python-deps.tar.gz

help:
	@echo "USB Encryption Enforcer - Build System"
	@echo ""
	@echo "RPM Targets:"
	@echo "  make rpm         - Build binary RPM (downloads deps during install)"
	@echo "  make rpm-bundled - Build binary RPM with bundled Python deps"
	@echo "  make srpm        - Build source RPM"
	@echo ""
	@echo "DEB Targets:"
	@echo "  make deb         - Build Debian package (downloads deps during install)"
	@echo "  make deb-bundled - Build Debian package with bundled Python deps"
	@echo ""
	@echo "Utility Targets:"
	@echo "  make dist        - Create source tarball"
	@echo "  make bundle-deps - Download Python dependencies as wheels"
	@echo "  make clean       - Remove build artifacts"
	@echo ""
	@echo "Package Variants:"
	@echo "  Standard: Smaller package, requires network during installation"
	@echo "  Bundled:  Larger package, works offline/airgapped"
	@echo ""
	@echo "Requirements:"
	@echo "  For RPM: rpm-build, rpmdevtools packages"
	@echo "  For DEB: debhelper, dh-python, devscripts packages"

dist: clean
	@echo "Creating source tarball $(TARBALL)..."
	@mkdir -p $(NAME)-$(VERSION)
	@cp -r src/ scripts/ deploy/ docs/ $(NAME)-$(VERSION)/
	@cp README.md requirements.txt $(NAME)-$(VERSION)/
	@tar czf $(TARBALL) $(NAME)-$(VERSION)
	@rm -rf $(NAME)-$(VERSION)
	@echo "Source tarball created: $(TARBALL)"

bundle-deps:
	@echo "Downloading Python dependencies as wheels..."
	@./scripts/bundle-python-deps.sh

prepare-rpm: dist
	@echo "Preparing RPM build environment..."
	@if [ ! -d ~/rpmbuild ]; then \
		echo "Setting up RPM build tree..."; \
		rpmdev-setuptree; \
	fi
	@cp $(TARBALL) ~/rpmbuild/SOURCES/
	@cp $(SPEC_FILE) ~/rpmbuild/SPECS/$(NAME).spec
	@echo "RPM build environment ready"

srpm: prepare-rpm
	@echo "Building source RPM..."
	@rpmbuild -bs ~/rpmbuild/SPECS/$(NAME).spec
	@echo ""
	@echo "Source RPM created in ~/rpmbuild/SRPMS/"
	@ls -lh ~/rpmbuild/SRPMS/$(NAME)-$(VERSION)-$(RELEASE)*.src.rpm

rpm: prepare-rpm
	@echo "Building binary RPM (standard version)..."
	@rpmbuild -bb ~/rpmbuild/SPECS/$(NAME).spec
	@mkdir -p dist
	@cp ~/rpmbuild/RPMS/noarch/$(NAME)-$(VERSION)-$(RELEASE).*.noarch.rpm dist/
	@echo ""
	@echo "Binary RPM created in dist/"
	@ls -lh dist/$(NAME)-$(VERSION)-*.noarch.rpm

rpm-bundled: dist bundle-deps
	@echo "Preparing bundled RPM build environment..."
	@if [ ! -d ~/rpmbuild ]; then \
		echo "Setting up RPM build tree..."; \
		rpmdev-setuptree; \
	fi
	@cp $(TARBALL) ~/rpmbuild/SOURCES/
	@cp $(PYTHON_DEPS) ~/rpmbuild/SOURCES/
	@cp $(SPEC_FILE_BUNDLED) ~/rpmbuild/SPECS/$(NAME_BUNDLED).spec
	@echo "Building bundled binary RPM..."
	@rpmbuild -bb ~/rpmbuild/SPECS/$(NAME_BUNDLED).spec
	@mkdir -p dist
	@cp ~/rpmbuild/RPMS/noarch/$(NAME_BUNDLED)-$(VERSION)-$(RELEASE).*.noarch.rpm dist/
	@echo ""
	@echo "Bundled binary RPM created in dist/"
	@ls -lh dist/$(NAME_BUNDLED)-$(VERSION)-*.noarch.rpm

clean:
	@echo "Cleaning build artifacts..."
	@rm -f $(TARBALL)
	@rm -f $(PYTHON_DEPS)
	@rm -rf dist/
	@rm -rf $(NAME)-$(VERSION)
	@rm -rf wheels/
	@rm -rf debian/.debhelper debian/debhelper-build-stamp debian/files debian/tmp
	@rm -rf debian/$(NAME) debian/$(NAME).debhelper.log debian/$(NAME).substvars
	@rm -rf debian-bundled/.debhelper debian-bundled/debhelper-build-stamp debian-bundled/files debian-bundled/tmp
	@rm -rf debian-bundled/$(NAME_BUNDLED) debian-bundled/$(NAME_BUNDLED).debhelper.log debian-bundled/$(NAME_BUNDLED).substvars
	@rm -f ~/rpmbuild/SOURCES/$(TARBALL) 2>/dev/null || true
	@rm -f ~/rpmbuild/SOURCES/$(PYTHON_DEPS) 2>/dev/null || true
	@rm -f ~/rpmbuild/SPECS/$(NAME).spec 2>/dev/null || true
	@rm -f ~/rpmbuild/SPECS/$(NAME_BUNDLED).spec 2>/dev/null || true
	@rm -f ~/rpmbuild/SRPMS/$(NAME)-$(VERSION)-$(RELEASE)*.src.rpm 2>/dev/null || true
	@rm -f ~/rpmbuild/RPMS/noarch/$(NAME)-$(VERSION)-$(RELEASE)*.noarch.rpm 2>/dev/null || true
	@echo "Clean complete"

deb:
	@if [ ! -f $(TARBALL) ]; then $(MAKE) dist; fi
	@echo "Building Debian package (standard version)..."
	@if ! command -v dpkg-buildpackage >/dev/null 2>&1; then \
		echo "Error: dpkg-buildpackage not found. Install: sudo apt install debhelper dh-python devscripts"; \
		exit 1; \
	fi
	@mkdir -p $(NAME)-$(VERSION)
	@tar xzf $(TARBALL)
	@cp -r debian $(NAME)-$(VERSION)/
	@cd $(NAME)-$(VERSION) && dpkg-buildpackage -us -uc -b
	@mkdir -p dist
	@mv $(NAME)_$(VERSION)-*.deb dist/ 2>/dev/null || true
	@rm -rf $(NAME)-$(VERSION)
	@rm -f $(NAME)_$(VERSION)-*.buildinfo $(NAME)_$(VERSION)-*.changes 2>/dev/null || true
	@echo ""
	@echo "Debian package created in dist/"
	@ls -lh dist/$(NAME)_$(VERSION)-*.deb

deb-bundled:
	@if [ ! -f $(TARBALL) ]; then $(MAKE) dist; fi
	@if [ ! -f $(PYTHON_DEPS) ]; then $(MAKE) bundle-deps; fi
	@echo "Building Debian package (bundled version)..."
	@if ! command -v dpkg-buildpackage >/dev/null 2>&1; then \
		echo "Error: dpkg-buildpackage not found. Install: sudo apt install debhelper dh-python devscripts"; \
		exit 1; \
	fi
	@mkdir -p $(NAME)-$(VERSION)
	@tar xzf $(TARBALL)
	@tar xzf $(PYTHON_DEPS)
	@cp -r wheels $(NAME)-$(VERSION)/
	@cp -r debian-bundled $(NAME)-$(VERSION)/debian
	@cd $(NAME)-$(VERSION) && dpkg-buildpackage -us -uc -b
	@mkdir -p dist
	@mv $(NAME_BUNDLED)_$(VERSION)-*.deb dist/ 2>/dev/null || true
	@rm -rf $(NAME)-$(VERSION)
	@rm -f $(NAME_BUNDLED)_$(VERSION)-*.buildinfo $(NAME_BUNDLED)_$(VERSION)-*.changes 2>/dev/null || true
	@echo ""
	@echo "Bundled Debian package created in dist/"
	@ls -lh dist/$(NAME_BUNDLED)_$(VERSION)-*.deb


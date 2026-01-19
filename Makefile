.PHONY: help rpm srpm clean prepare-rpm dist rpm-bundled bundle-deps deb deb-bundled rpm-admin deb-admin rpm-all deb-all test test-unit test-integration test-coverage test-lint test-all

NAME := usb-enforcer
NAME_BUNDLED := usb-enforcer-bundled
NAME_ADMIN := usb-enforcer-admin
VERSION := $(shell ./scripts/build-version.sh)
RELEASE := 1
TARBALL := $(NAME)-$(VERSION).tar.gz
SPEC_FILE := rpm/usb-enforcer.spec
SPEC_FILE_BUNDLED := rpm-bundled/usb-enforcer-bundled.spec
SPEC_FILE_ADMIN := rpm-admin/usb-enforcer-admin.spec
PYTHON_DEPS := python-deps.tar.gz

help:
	@echo "USB Enforcer - Build System"
	@echo ""
	@echo "RPM Targets:"
	@echo "  make rpm         - Build binary RPM (downloads deps during install)"
	@echo "  make rpm-bundled - Build binary RPM with bundled Python deps"
	@echo "  make rpm-admin   - Build admin GUI RPM (separate package)"
	@echo "  make rpm-all     - Build all RPM packages (standard, bundled, admin)"
	@echo "  make srpm        - Build source RPM"
	@echo ""
	@echo "DEB Targets:"
	@echo "  make deb         - Build Debian package (downloads deps during install)"
	@echo "  make deb-bundled - Build Debian package with bundled Python deps"
	@echo "  make deb-admin   - Build admin GUI Debian package (separate package)"
	@echo "  make deb-all     - Build all Debian packages (standard, bundled, admin)"
	@echo ""
	@echo "Admin GUI Targets:"
	@echo "  make admin-install - Install admin GUI directly (no package)"
	@echo ""
	@echo "Test Targets:"
	@echo "  make test            - Run unit tests (no root required)"
	@echo "  make test-unit       - Run unit tests"
	@echo "  make test-integration- Run integration tests (requires root)"
	@echo "  make test-coverage   - Run tests with coverage report"
	@echo "  make test-lint       - Run code quality checks"
	@echo "  make test-all        - Run all tests and checks"
	@echo ""
	@echo "Translation Targets:"
	@echo "  make translations    - Compile all translation files"
	@echo ""
	@echo "Utility Targets:"
	@echo "  make dist        - Create source tarball"
	@echo "  make bundle-deps - Download Python dependencies as wheels"
	@echo "  make clean       - Remove build artifacts"
	@echo ""
	@echo "Package Variants:"
	@echo "  Standard: Smaller package, requires network during installation"
	@echo "  Bundled:  Larger package, works offline/airgapped"
	@echo "  Admin:    Standalone GUI for config.toml editing"
	@echo ""
	@echo "Requirements:"
	@echo "  For RPM: rpm-build, rpmdevtools packages"
	@echo "  For DEB: debhelper, dh-python, devscripts packages"
	@echo "  For Tests: pip install -r requirements-test.txt"

dist:
	@echo "Creating source tarball $(TARBALL)..."
	@rm -rf $(NAME)-$(VERSION)
	@mkdir -p $(NAME)-$(VERSION)
	@cp -r src/ scripts/ deploy/ docs/ locale/ rpm/ rpm-bundled/ rpm-admin/ debian/ debian-bundled/ debian-admin/ $(NAME)-$(VERSION)/
	@cp README.md requirements.txt VERSION LICENSE $(NAME)-$(VERSION)/
	@./scripts/prepare-build-dir.sh $(NAME)-$(VERSION) $(VERSION)
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
	@sed 's/^Version:\s\+.*/Version:        $(VERSION)/' $(SPEC_FILE) > ~/rpmbuild/SPECS/$(NAME).spec
	@echo "RPM build environment ready"

srpm: prepare-rpm
	@echo "Building source RPM..."
	@rpmbuild -bs ~/rpmbuild/SPECS/$(NAME).spec
	@echo ""
	@echo "Source RPM created in ~/rpmbuild/SRPMS/"
	@ls -lh ~/rpmbuild/SRPMS/$(NAME)-$(VERSION)-*.src.rpm

rpm: prepare-rpm
	@echo "Building binary RPM (standard version)..."
	@rm -f ~/rpmbuild/RPMS/noarch/$(NAME)-$(VERSION)-*.noarch.rpm
	@rpmbuild -bb ~/rpmbuild/SPECS/$(NAME).spec
	@mkdir -p dist
	@cp ~/rpmbuild/RPMS/noarch/$(NAME)-$(VERSION)-*.noarch.rpm dist/
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
	@sed 's/^Version:\s\+.*/Version:        $(VERSION)/' $(SPEC_FILE_BUNDLED) > ~/rpmbuild/SPECS/$(NAME_BUNDLED).spec
	@echo "Building bundled binary RPM..."
	@rm -f ~/rpmbuild/RPMS/noarch/$(NAME_BUNDLED)-$(VERSION)-*.noarch.rpm
	@rpmbuild -bb ~/rpmbuild/SPECS/$(NAME_BUNDLED).spec
	@mkdir -p dist
	@cp ~/rpmbuild/RPMS/noarch/$(NAME_BUNDLED)-$(VERSION)-*.noarch.rpm dist/
	@echo ""
	@echo "Bundled binary RPM created in dist/"
	@ls -lh dist/$(NAME_BUNDLED)-$(VERSION)-*.noarch.rpm

clean:
	@echo "Cleaning build artifacts..."
	@rm -f $(TARBALL)
	@rm -f $(PYTHON_DEPS)
	@rm -f dist/$(NAME)-*.rpm dist/$(NAME_BUNDLED)-*.rpm dist/$(NAME_ADMIN)-*.rpm 2>/dev/null || true
	@rm -f dist/$(NAME)_*.deb dist/$(NAME_BUNDLED)_*.deb dist/$(NAME_ADMIN)_*.deb 2>/dev/null || true
	@rm -f dist/*.buildinfo dist/*.changes 2>/dev/null || true
	@rm -rf $(NAME)-$(VERSION)
	@rm -rf wheels/
	@rm -rf debian/.debhelper debian/debhelper-build-stamp debian/files debian/tmp
	@rm -rf debian/$(NAME) debian/$(NAME).debhelper.log debian/$(NAME).substvars
	@rm -rf debian-bundled/.debhelper debian-bundled/debhelper-build-stamp debian-bundled/files debian-bundled/tmp
	@rm -rf debian-bundled/$(NAME_BUNDLED) debian-bundled/$(NAME_BUNDLED).debhelper.log debian-bundled/$(NAME_BUNDLED).substvars
	@rm -rf debian-admin/.debhelper debian-admin/debhelper-build-stamp debian-admin/files debian-admin/tmp
	@rm -rf debian-admin/$(NAME_ADMIN) debian-admin/$(NAME_ADMIN).debhelper.log debian-admin/$(NAME_ADMIN).substvars
	@rm -f ~/rpmbuild/SOURCES/$(TARBALL) 2>/dev/null || true
	@rm -f ~/rpmbuild/SOURCES/$(PYTHON_DEPS) 2>/dev/null || true
	@rm -f ~/rpmbuild/SPECS/$(NAME).spec 2>/dev/null || true
	@rm -f ~/rpmbuild/SPECS/$(NAME_BUNDLED).spec 2>/dev/null || true
	@rm -f ~/rpmbuild/SPECS/$(NAME_ADMIN).spec 2>/dev/null || true
	@rm -f ~/rpmbuild/SRPMS/$(NAME)-$(VERSION)-$(RELEASE)*.src.rpm 2>/dev/null || true
	@rm -f ~/rpmbuild/RPMS/noarch/$(NAME)-$(VERSION)-$(RELEASE)*.noarch.rpm 2>/dev/null || true
	@rm -f ~/rpmbuild/RPMS/noarch/$(NAME_ADMIN)-$(VERSION)-$(RELEASE)*.noarch.rpm 2>/dev/null || true
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
	@mv $(NAME)_*.deb dist/ 2>/dev/null || true
	@rm -rf $(NAME)-$(VERSION)
	@rm -f $(NAME)_*.buildinfo $(NAME)_*.changes 2>/dev/null || true
	@echo ""
	@echo "Debian package created in dist/"
	@ls -lh dist/$(NAME)_*.deb

deb-bundled:
	@if [ ! -f $(TARBALL) ]; then $(MAKE) dist; fi
	@if [ ! -f $(PYTHON_DEPS) ]; then $(MAKE) bundle-deps; fi
	@echo "Building Debian package (bundled version)..."
	@if ! command -v dpkg-buildpackage >/dev/null 2>&1; then \
		echo "Error: dpkg-buildpackage not found. Install: sudo apt install debhelper dh-python devscripts"; \
		exit 1; \
	fi
	@mkdir -p $(NAME_BUNDLED)-$(VERSION)
	@tar xzf $(TARBALL)
	@tar xzf $(PYTHON_DEPS)
	@mv $(NAME)-$(VERSION)/* $(NAME_BUNDLED)-$(VERSION)/
	@rmdir $(NAME)-$(VERSION)
	@rm -rf $(NAME_BUNDLED)-$(VERSION)/debian
	@cp -r debian-bundled $(NAME_BUNDLED)-$(VERSION)/debian
	@cp -r wheels $(NAME_BUNDLED)-$(VERSION)/
	@cd $(NAME_BUNDLED)-$(VERSION) && dpkg-buildpackage -us -uc -b
	@mkdir -p dist
	@mv $(NAME_BUNDLED)_*.deb dist/ 2>/dev/null || true
	@rm -rf $(NAME_BUNDLED)-$(VERSION)
	@rm -f $(NAME_BUNDLED)_*.buildinfo $(NAME_BUNDLED)_*.changes 2>/dev/null || true
	@echo ""
	@echo "Bundled Debian package created in dist/"
	@ls -lh dist/$(NAME_BUNDLED)_*.deb

# Admin GUI package targets
rpm-admin: prepare-rpm
	@echo "Building admin GUI RPM..."
	@if [ ! -d ~/rpmbuild ]; then \
		echo "Setting up RPM build tree..."; \
		rpmdev-setuptree; \
	fi
	@sed 's/^Version:\s\+.*/Version:        $(VERSION)/' $(SPEC_FILE_ADMIN) > ~/rpmbuild/SPECS/$(NAME_ADMIN).spec
	@rm -f ~/rpmbuild/RPMS/noarch/$(NAME_ADMIN)-$(VERSION)-*.noarch.rpm
	@rpmbuild -bb ~/rpmbuild/SPECS/$(NAME_ADMIN).spec
	@mkdir -p dist
	@cp ~/rpmbuild/RPMS/noarch/$(NAME_ADMIN)-$(VERSION)-*.noarch.rpm dist/
	@echo ""
	@echo "Admin GUI RPM created in dist/"
	@ls -lh dist/$(NAME_ADMIN)-$(VERSION)-*.noarch.rpm

deb-admin:
	@if [ ! -f $(TARBALL) ]; then $(MAKE) dist; fi
	@echo "Building admin GUI Debian package..."
	@if ! command -v dpkg-buildpackage >/dev/null 2>&1; then \
		echo "Error: dpkg-buildpackage not found. Install: sudo apt install debhelper dh-python devscripts"; \
		exit 1; \
	fi
	@mkdir -p $(NAME_ADMIN)-$(VERSION)
	@tar xzf $(TARBALL)
	@mv $(NAME)-$(VERSION)/* $(NAME_ADMIN)-$(VERSION)/
	@rmdir $(NAME)-$(VERSION)
	@rm -rf $(NAME_ADMIN)-$(VERSION)/debian
	@cp -r debian-admin $(NAME_ADMIN)-$(VERSION)/debian
	@cp setup-admin.py $(NAME_ADMIN)-$(VERSION)/setup.py
	@cd $(NAME_ADMIN)-$(VERSION) && dpkg-buildpackage -us -uc -b
	@mkdir -p dist
	@mv $(NAME_ADMIN)_*.deb dist/ 2>/dev/null || true
	@rm -rf $(NAME_ADMIN)-$(VERSION)
	@rm -f $(NAME_ADMIN)_*.buildinfo $(NAME_ADMIN)_*.changes 2>/dev/null || true
	@echo ""
	@echo "Admin GUI Debian package created in dist/"
	@ls -lh dist/$(NAME_ADMIN)_*.deb

# Build all package variants
rpm-all: rpm rpm-bundled rpm-admin
	@echo ""
	@echo "========================================"
	@echo "All RPM packages built successfully!"
	@echo "========================================"
	@echo ""
	@ls -lh dist/*.rpm

deb-all: deb deb-bundled deb-admin
	@echo ""
	@echo "========================================"
	@echo "All Debian packages built successfully!"
	@echo "========================================"
	@echo ""
	@ls -lh dist/*.deb

admin-install:
	@echo "Installing admin GUI directly..."
	@bash scripts/install-admin.sh

# Test targets
test: test-unit

test-unit:
	@echo "Running unit tests..."
	@./run-tests.sh unit

test-integration:
	@echo "Running integration tests (requires root)..."
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "Error: Integration tests require root privileges"; \
		echo "Run with: sudo make test-integration"; \
		exit 1; \
	fi
	@./run-tests.sh integration

test-coverage:
	@echo "Running tests with coverage..."
	@./run-tests.sh coverage

test-lint:
	@echo "Running code quality checks..."
	@./run-tests.sh lint

test-all:
	@echo "Running all tests and checks..."
	@./run-tests.sh all

# Translation targets
translations:
	@echo "Compiling translation files..."
	@for po in locale/*/LC_MESSAGES/*.po; do \
		mo=$${po%.po}.mo; \
		echo "  Compiling $${po}..."; \
		msgfmt $$po -o $$mo; \
	done
	@echo "Translation files compiled"

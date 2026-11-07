#!/bin/sh
# CI only: installs what Xero Wallpapers needs inside the Arch Linux build container.
set -eu

pacman -Syu --noconfirm --needed \
	breeze-icons \
	curl \
	kirigami \
	python \
	python-beautifulsoup4 \
	python-pillow \
	python-pyqt6 \
	python-requests \
	python-soupsieve \
	python-urllib3 \
	qqc2-desktop-style \
	qt6-declarative \
	qt6-imageformats \
	qt6-multimedia \
	qt6-multimedia-ffmpeg \
	qt6-svg \
	qt6-wayland

get-debloated-pkgs --add-common --prefer-nano

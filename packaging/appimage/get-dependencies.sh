#!/bin/sh
# CI only: installs what Xero Wallpapers needs inside the Arch Linux build container.
set -eu

# The container only lists pkgforge's mirror; official mirrors after it keep builds going when that one is down.
case "$(uname -m)" in
	x86_64) printf 'Server = %s\n' 'https://geo.mirror.pkgbuild.com/$repo/os/$arch' 'https://mirrors.kernel.org/archlinux/$repo/os/$arch' >> /etc/pacman.d/mirrorlist ;;
	aarch64) printf 'Server = %s\n' 'http://mirror.archlinuxarm.org/$arch/$repo' >> /etc/pacman.d/mirrorlist ;;
esac

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

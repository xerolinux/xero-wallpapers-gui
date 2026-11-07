#!/bin/sh
# Regenerate the slideshow plugin's .qsb files after editing a .frag source.
set -e
QSB="${QSB:-/usr/lib/qt6/bin/qsb}"
cd "$(dirname "$0")/org.xerolinux.wallpapers.slideshow/contents/ui/shaders"
for frag in *.frag; do
    "$QSB" --qt6 -o "$frag.qsb" "$frag"
done

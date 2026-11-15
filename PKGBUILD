# Maintainer: XeroLinux <xero@xerolinux.xyz>
pkgname=xero-wallpaper-browser
pkgver=2.0.10
pkgrel=1
pkgdesc="Browse, preview, upscale and set wallpapers and live wallpapers on KDE Plasma"
arch=('any')
url="https://github.com/xerolinux/xero-wallpapers-gui"
license=('GPL-3.0-or-later')
depends=(
  'python'
  'python-pyqt6'
  'qt6-declarative'
  'qt6-multimedia'
  'qt6-multimedia-ffmpeg'
  'qt6-imageformats'
  'kirigami'
  'qqc2-desktop-style'
  'kvantum'
  'noto-fonts'
  'breeze-icons'
  'python-requests'
  'python-urllib3'
  'python-beautifulsoup4'
  'python-soupsieve'
  'python-pillow'
  'python-numpy'
  'python-onnxruntime-cpu'
)
optdepends=(
  'plasma-workspace: set wallpapers and live wallpapers on KDE Plasma, and the Xero Slideshow plugin'
  'polkit: pkexec to install missing live wallpaper dependencies'
  'vulkan-tools: detect a dedicated GPU for AI upscaling'
)
source=(
  'xero_wallpaper_browser.py'
  'xero_logo.png'
  'xero-wallpaper-browser.desktop'
  # CLIP ViT-B/32 image encoder (MIT) for the No anime filter.
  "clip-vision.onnx::https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/6b7c523703ae26e39be4b03774966f8571c7f523/onnx/vision_model_quantized.onnx"
)
sha256sums=('SKIP' 'SKIP' 'SKIP'
            '583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299')

package() {
  local libdir="$pkgdir/usr/lib/$pkgname"

  install -Dm755 "$srcdir/xero_wallpaper_browser.py" "$libdir/xero_wallpaper_browser.py"
  install -Dm644 "$srcdir/xero_logo.png" "$libdir/xero_logo.png"

  # makepkg cannot take a directory as a source, so the package tree is copied from the PKGBUILD folder.
  cp -r "$startdir/xero_wallpapers" "$libdir/"
  find "$libdir/xero_wallpapers" -name '__pycache__' -type d -prune -exec rm -rf {} +
  rm -rf "$libdir/xero_wallpapers/data/models"
  install -Dm644 "$srcdir/clip-vision.onnx" "$libdir/xero_wallpapers/data/models/clip-vision.onnx"
  find "$libdir/xero_wallpapers" -type d -exec chmod 755 {} +
  find "$libdir/xero_wallpapers" -type f -exec chmod 644 {} +

  # Only the compiled .qsb shaders are loaded, so the .frag sources stay out of the package.
  local plugin="$pkgdir/usr/share/plasma/wallpapers/org.xerolinux.wallpapers.slideshow"
  install -Dm644 "$startdir/plasma/org.xerolinux.wallpapers.slideshow/metadata.json" "$plugin/metadata.json"
  cp -r "$startdir/plasma/org.xerolinux.wallpapers.slideshow/contents" "$plugin/"
  find "$plugin" -name '*.frag' -delete
  find "$plugin" -type d -exec chmod 755 {} +
  find "$plugin" -type f -exec chmod 644 {} +

  install -Dm644 "$srcdir/xero_logo.png" \
    "$pkgdir/usr/share/icons/hicolor/256x256/apps/$pkgname.png"
  install -Dm644 "$srcdir/$pkgname.desktop" \
    "$pkgdir/usr/share/applications/$pkgname.desktop"

  install -dm755 "$pkgdir/usr/bin"
  cat > "$pkgdir/usr/bin/$pkgname" << 'LAUNCHER'
#!/bin/bash
exec python /usr/lib/xero-wallpaper-browser/xero_wallpaper_browser.py "$@"
LAUNCHER
  chmod 755 "$pkgdir/usr/bin/$pkgname"
}

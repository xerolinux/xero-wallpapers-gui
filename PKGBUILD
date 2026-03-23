# Maintainer: XeroLinux <xero@xerolinux.xyz>
pkgname=xero-wallpaper-browser
pkgver=1.0.0
pkgrel=1
pkgdesc="Browse, preview and download wallpapers & live wallpapers from various sources"
arch=('any')
url="https://github.com/xerolinux/xero-wallpaper-browser"
license=('GPL-3.0-or-later')
depends=(
  'python'
  'python-pyqt6'
  'python-requests'
  'python-beautifulsoup4'
  'python-pillow'
  'python-opencv'
  'python-numpy'
  'qt6-multimedia'
  'qt6-multimedia-gstreamer'
  'gst-plugins-good'
  'gst-plugins-bad'
  'gst-libav'
)
source=(
  'xero_wallpaper_browser.py'
  'xero_logo.png'
  'xero-wallpaper-browser.desktop'
)
sha256sums=('SKIP' 'SKIP' 'SKIP')

package() {
  # Install main application
  install -Dm755 "$srcdir/xero_wallpaper_browser.py" \
    "$pkgdir/usr/lib/$pkgname/xero_wallpaper_browser.py"

  # Install logo
  install -Dm644 "$srcdir/xero_logo.png" \
    "$pkgdir/usr/lib/$pkgname/xero_logo.png"

  # Install icon (multiple sizes)
  install -Dm644 "$srcdir/xero_logo.png" \
    "$pkgdir/usr/share/icons/hicolor/256x256/apps/$pkgname.png"

  # Install desktop entry
  install -Dm644 "$srcdir/$pkgname.desktop" \
    "$pkgdir/usr/share/applications/$pkgname.desktop"

  # Install launcher script
  install -dm755 "$pkgdir/usr/bin"
  cat > "$pkgdir/usr/bin/$pkgname" << 'EOF'
#!/bin/bash
exec python /usr/lib/xero-wallpaper-browser/xero_wallpaper_browser.py "$@"
EOF
  chmod 755 "$pkgdir/usr/bin/$pkgname"
}

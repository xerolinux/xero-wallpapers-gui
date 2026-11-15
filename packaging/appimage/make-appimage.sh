#!/bin/sh
# Builds Xero Wallpapers as a self-contained AppImage (bundled Python, PyQt6, Qt 6, QML, Kirigami and glibc)
# with quick-sharun from https://github.com/pkgforge-dev/Anylinux-AppImages.
# The build system needs the PKGBUILD dependencies installed; CI installs them with get-dependencies.sh.
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
ARCH=$(uname -m)
VERSION=$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' "$ROOT/xero_wallpapers/__init__.py")
WORK=${WORK:-$ROOT/build/appimage}
SHARE_NAME=xero-wallpaper-browser
QUICK_SHARUN_URL="https://raw.githubusercontent.com/pkgforge-dev/Anylinux-AppImages/refs/heads/main/useful-tools/quick-sharun.sh"
# CLIP ViT-B/32 image encoder (Xenova/clip-vit-base-patch32, MIT) for the No anime filter, pinned by revision and hash.
CLIP_URL="https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/6b7c523703ae26e39be4b03774966f8571c7f523/onnx/vision_model_quantized.onnx"
CLIP_SHA256=583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299

export ARCH VERSION
export APPDIR="$WORK/AppDir"
export OUTPATH="${OUTPATH:-$ROOT/dist}"
export OUTNAME="Xero_Wallpapers-$VERSION-$ARCH.AppImage"
export ICON="$WORK/$SHARE_NAME.png"
export DESKTOP="$ROOT/$SHARE_NAME.desktop"
export DEPLOY_PYTHON=1
export DEPLOY_QT=1
export DEPLOY_QML=1
export DEPLOY_PULSE=1
if [ -n "${GITHUB_REPOSITORY:-}" ]; then
	export UPINFO="gh-releases-zsync|${GITHUB_REPOSITORY%/*}|${GITHUB_REPOSITORY#*/}|latest|*$ARCH.AppImage.zsync"
fi

rm -rf "$APPDIR"
mkdir -p "$WORK" "$APPDIR/bin" "$APPDIR/share/$SHARE_NAME/plasma"

python3 - "$ROOT/xero_logo.png" "$ICON" <<'PY'
import sys
from PIL import Image
logo = Image.open(sys.argv[1]).convert("RGBA")
logo.thumbnail((256, 256), Image.LANCZOS)
icon = Image.new("RGBA", (256, 256))
icon.paste(logo, ((256 - logo.width) // 2, (256 - logo.height) // 2))
icon.save(sys.argv[2])
PY

# slideshow.py finds the Plasma plugin next to the package, as in a source checkout.
cp -r "$ROOT/xero_wallpaper_browser.py" "$ROOT/xero_logo.png" "$ROOT/xero_wallpapers" "$APPDIR/share/$SHARE_NAME/"
cp -r "$ROOT/plasma/org.xerolinux.wallpapers.slideshow" "$APPDIR/share/$SHARE_NAME/plasma/"
find "$APPDIR/share/$SHARE_NAME" -name __pycache__ -type d -prune -exec rm -rf {} +
# theme.py loads these when the host has no Noto Sans, so text looks the same everywhere.
mkdir -p "$APPDIR/share/$SHARE_NAME/xero_wallpapers/data/fonts"
cp /usr/share/fonts/noto/NotoSans-Regular.ttf /usr/share/fonts/noto/NotoSans-Italic.ttf \
	/usr/share/fonts/noto/NotoSans-Medium.ttf /usr/share/fonts/noto/NotoSans-Bold.ttf \
	"$APPDIR/share/$SHARE_NAME/xero_wallpapers/data/fonts/"
find "$APPDIR/share/$SHARE_NAME/plasma" -name '*.frag' -delete
rm -rf "$APPDIR/share/$SHARE_NAME/xero_wallpapers/data/models"
ONNX_LIBS=""
if python3 -c 'import onnxruntime' 2>/dev/null; then
	CLIP="$WORK/clip-vision.onnx"
	if ! echo "$CLIP_SHA256  $CLIP" | sha256sum -c --status 2>/dev/null; then
		curl -fsSL "$CLIP_URL" -o "$CLIP"
		echo "$CLIP_SHA256  $CLIP" | sha256sum -c -
	fi
	install -Dm644 "$CLIP" "$APPDIR/share/$SHARE_NAME/xero_wallpapers/data/models/clip-vision.onnx"
	ONNX_LIBS=$(find /usr/lib/python3*/site-packages/onnxruntime/capi -name '*.so*')
fi
cat > "$APPDIR/bin/$SHARE_NAME" <<'SH'
#!/bin/sh
exec python3 "$APPDIR/share/xero-wallpaper-browser/xero_wallpaper_browser.py" "$@"
SH
chmod +x "$APPDIR/bin/$SHARE_NAME"

cd "$WORK"
QUICK_SHARUN=$(command -v quick-sharun || true)
if [ -z "$QUICK_SHARUN" ]; then
	QUICK_SHARUN="$WORK/quick-sharun"
	[ -x "$QUICK_SHARUN" ] || { curl -fsSL "$QUICK_SHARUN_URL" -o "$QUICK_SHARUN" && chmod +x "$QUICK_SHARUN"; }
fi

# quick-sharun skips _ssl and _hashlib (HTTPS needs both) and does not scan site-packages for libraries. Plugins
# are picked from the libraries the arguments link against, which misses those only QML pulls in: the
# QtMultimedia FFmpeg backend, Kirigami's desktop theme, and the libraries behind the KDE QML plugins. Without
# the last, hosts fall back to their own Kirigami libraries, which need a different Qt's private API.
KDE_QML_PLUGINS=$(find /usr/lib/qt6/qml/org/kde/kirigami /usr/lib/qt6/qml/org/kde/desktop \
	/usr/lib/qt6/qml/org/kde/qqc2desktopstyle /usr/lib/qt6/qml/org/kde/sonnet /usr/lib/qt6/qml/org/kde/union \
	-name '*.so' 2>/dev/null || true)
# shellcheck disable=SC2086
"$QUICK_SHARUN" \
	$KDE_QML_PLUGINS \
	$ONNX_LIBS \
	/usr/bin/python3 \
	/usr/lib/python3*/lib-dynload/_ssl*.so \
	/usr/lib/python3*/lib-dynload/_hashlib*.so \
	/usr/lib/python3*/site-packages/PyQt6/sip*.so \
	/usr/lib/python3*/site-packages/PyQt6/QtCore.abi3.so \
	/usr/lib/python3*/site-packages/PyQt6/QtGui.abi3.so \
	/usr/lib/python3*/site-packages/PyQt6/QtWidgets.abi3.so \
	/usr/lib/python3*/site-packages/PyQt6/QtNetwork.abi3.so \
	/usr/lib/python3*/site-packages/PyQt6/QtQml.abi3.so \
	/usr/lib/python3*/site-packages/PyQt6/QtQuick.abi3.so \
	/usr/lib/python3*/site-packages/PyQt6/QtDBus.abi3.so \
	/usr/lib/python3*/site-packages/PIL/*.so \
	/usr/lib/qt6/plugins/multimedia \
	/usr/lib/qt6/plugins/styles/libkvantum.so \
	/usr/lib/qt6/plugins/wayland-decoration-client \
	/usr/lib/qt6/plugins/kf6/kirigami

# Breeze Dark (and Breeze, which it inherits) for hosts without a Breeze icon theme.
mkdir -p "$APPDIR/share/icons"
cp -r /usr/share/icons/breeze /usr/share/icons/breeze-dark "$APPDIR/share/icons/"

"$QUICK_SHARUN" --make-appimage

if [ "${SKIP_TEST:-0}" != 1 ]; then
	"$QUICK_SHARUN" --test "$OUTPATH/$OUTNAME"
fi

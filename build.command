#!/bin/zsh
set -e
cd "$(dirname "$0")"
swiftc -framework Cocoa CodexTrafficLight.swift -o CodexTrafficLight

APP="CodexTaskTrafficLight.app"
CONTENTS="$APP/Contents"
mkdir -p "$CONTENTS/MacOS"
cp CodexTrafficLight "$CONTENTS/MacOS/CodexTrafficLight"
cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>CodexTrafficLight</string>
  <key>CFBundleIdentifier</key>
  <string>com.ss.codex-traffic-light</string>
  <key>CFBundleName</key>
  <string>Codex Task Traffic Light</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>LSUIElement</key>
  <true/>
</dict>
</plist>
PLIST

mkdir -p dist
ditto -c -k --sequesterRsrc --keepParent "$APP" "dist/CodexTaskTrafficLight-macOS.zip"
echo "已生成 CodexTaskTrafficLight.app 和 dist/CodexTaskTrafficLight-macOS.zip"

#!/bin/sh
# Run from the extracted source tree. Both packages use this installation layout.
set -eu
root=${1:?missing package staging directory}
install -d "$root/usr/share/ratcommander/aerocommand" "$root/usr/bin"
install -m644 src/aerocommand/*.py "$root/usr/share/ratcommander/aerocommand/"
cat > "$root/usr/bin/ratcommander" <<'PY'
#!/usr/bin/python3
import sys
sys.path.insert(0, "/usr/share/ratcommander")
from aerocommand.__main__ import main
sys.exit(main())
PY
chmod 755 "$root/usr/bin/ratcommander"
ln -s ratcommander "$root/usr/bin/aerocommand"
install -Dm644 LICENSE "$root/usr/share/licenses/ratcommander/LICENSE"
install -Dm644 packaging/70-aerocommand.rules "$root/usr/lib/udev/rules.d/70-aerocommand.rules"
install -Dm644 packaging/ratcommander.desktop "$root/usr/share/applications/ratcommander.desktop"

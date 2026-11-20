#!/usr/bin/env bash
# Run in the checkout to package HEAD. Outputs go in the directory supplied.
set -euo pipefail
format=${1:?expected arch or ubuntu}
output=$(realpath -m "${2:?expected output directory}")
cd "$(git rev-parse --show-toplevel)"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git archive --format=tar.gz --prefix=RatCommander/ -o "$work/source.tar.gz" HEAD
cd "$work"
tar xzf source.tar.gz
src=$work/RatCommander
version=$(python3 -c 'import tomllib; print(tomllib.load(open("RatCommander/pyproject.toml","rb"))["project"]["version"])')
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Expected a three-part numeric version" >&2; exit 1; }
[[ ${RELEASE_TAG:-v$version} == "v$version" ]] || { echo "Release tag must match v$version" >&2; exit 1; }
mkdir -p "$output"
case "$format" in
    arch)
        checksum=$(sha256sum source.tar.gz | cut -d' ' -f1)
        sed -e "s/@VERSION@/$version/g" -e "s/@SHA256@/$checksum/g" "$src/packaging/arch/PKGBUILD.in" > PKGBUILD
        PKGDEST="$output" makepkg --nodeps
        ;;
    ubuntu)
        cd "$src"
        root=$work/pkg
        sh packaging/install-tree.sh "$root"
        install -d "$root/DEBIAN" "$root/usr/share/doc/ratcommander"
        install -m644 LICENSE "$root/usr/share/doc/ratcommander/copyright"
        cat > "$root/DEBIAN/control" <<CONTROL
Package: ratcommander
Version: $version-1
Architecture: all
Maintainer: RatCommander maintainers <galdorork@users.noreply.github.com>
Section: utils
Priority: optional
Depends: python3 (>= 3.11), python3-pyside6.qtwidgets (>= 6.6), python3-hid (>= 0.14)
Description: Desktop configurator for the SteelSeries Aerox 9 Wireless mouse
CONTROL
        dpkg-deb --root-owner-group --build "$root" "$output/ratcommander_${version}-1_all.deb"
        ;;
    *) echo "Expected arch or ubuntu" >&2; exit 2 ;;
esac

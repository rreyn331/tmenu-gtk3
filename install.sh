#!/bin/bash

set -e

echo "Rebuilding and installing..."

dpkg-buildpackage -us -uc -b >/dev/null

sudo dpkg -i ../tmenu_*_all.deb

echo "Installed"
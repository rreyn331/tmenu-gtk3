#!/bin/bash

set -e

echo "Building package..."

dpkg-buildpackage -us -uc -b

echo "Build complete"
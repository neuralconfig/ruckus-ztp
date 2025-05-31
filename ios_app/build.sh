#!/bin/bash

# Build script for RuckusZTP iOS app
# This script helps build the app from command line

echo "Building RuckusZTP iOS app..."

# Check if Xcode is installed
if ! command -v xcodebuild &> /dev/null; then
    echo "Error: Xcode is required to build this project"
    echo "Please install Xcode from the Mac App Store"
    exit 1
fi

# Navigate to project directory
cd "$(dirname "$0")"

# Clean build folder
echo "Cleaning build folder..."
xcodebuild clean -project RuckusZTP.xcodeproj -scheme RuckusZTP

# Build for simulator
echo "Building for iOS Simulator..."
xcodebuild build \
    -project RuckusZTP.xcodeproj \
    -scheme RuckusZTP \
    -sdk iphonesimulator \
    -configuration Debug \
    -derivedDataPath build/

if [ $? -eq 0 ]; then
    echo "Build succeeded!"
    echo "You can now open the project in Xcode to run on simulator or device"
else
    echo "Build failed. Please check the error messages above."
    exit 1
fi
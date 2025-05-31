#!/bin/bash

# Script to create iOS project structure that can be opened in Xcode
# Run this script, then open Xcode and create a new iOS project in this directory

echo "Creating iOS project structure for RuckusZTP..."

# Create directory structure
mkdir -p RuckusZTP/{Models,Views,Managers,Services}
mkdir -p RuckusZTP.xcodeproj

# Create Info.plist
cat > RuckusZTP/Info.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>$(DEVELOPMENT_LANGUAGE)</string>
	<key>CFBundleExecutable</key>
	<string>$(EXECUTABLE_NAME)</string>
	<key>CFBundleIdentifier</key>
	<string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>$(PRODUCT_NAME)</string>
	<key>CFBundlePackageType</key>
	<string>$(PRODUCT_BUNDLE_PACKAGE_TYPE)</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0</string>
	<key>CFBundleVersion</key>
	<string>1</string>
	<key>LSRequiresIPhoneOS</key>
	<true/>
	<key>UIApplicationSceneManifest</key>
	<dict>
		<key>UIApplicationSupportsMultipleScenes</key>
		<false/>
		<key>UISceneConfigurations</key>
		<dict>
			<key>UIWindowSceneSessionRoleApplication</key>
			<array>
				<dict>
					<key>UISceneConfigurationName</key>
					<string>Default Configuration</string>
					<key>UISceneDelegateClassName</key>
					<string>$(PRODUCT_MODULE_NAME).SceneDelegate</string>
					<key>UISceneStoryboardFile</key>
					<string>Main</string>
				</dict>
			</array>
		</dict>
	</dict>
	<key>UIApplicationSupportsIndirectInputEvents</key>
	<true/>
	<key>UILaunchStoryboardName</key>
	<string>LaunchScreen</string>
	<key>UIMainStoryboardFile</key>
	<string>Main</string>
	<key>UIRequiredDeviceCapabilities</key>
	<array>
		<string>armv7</string>
	</array>
	<key>UISupportedInterfaceOrientations</key>
	<array>
		<string>UIInterfaceOrientationPortrait</string>
		<string>UIInterfaceOrientationLandscapeLeft</string>
		<string>UIInterfaceOrientationLandscapeRight</string>
	</array>
	<key>UISupportedInterfaceOrientations~ipad</key>
	<array>
		<string>UIInterfaceOrientationPortrait</string>
		<string>UIInterfaceOrientationPortraitUpsideDown</string>
		<string>UIInterfaceOrientationLandscapeLeft</string>
		<string>UIInterfaceOrientationLandscapeRight</string>
	</array>
</dict>
</plist>
EOF

echo "✅ Created iOS project structure"
echo "🔧 Next steps:"
echo "1. Open Xcode"
echo "2. File > New > Project"
echo "3. Choose iOS > App"
echo "4. Use these settings:"
echo "   - Product Name: RuckusZTP"
echo "   - Bundle Identifier: com.neuralconfig.RuckusZTP"
echo "   - Language: Swift"
echo "   - Interface: SwiftUI"
echo "   - Save to: $(pwd)"
echo "5. Replace the generated files with the source files we created"

# Copy our Swift files if they exist in the old location
if [ -d "../ios_app_backup/RuckusZTP" ]; then
    echo "📁 Copying existing Swift files..."
    cp -r ../ios_app_backup/RuckusZTP/* RuckusZTP/
fi

echo "📱 The project will have all the features from the web interface:"
echo "   - Configuration management"
echo "   - Real-time monitoring"
echo "   - Network topology visualization"
echo "   - AI-powered chat interface"
echo "   - Log viewing and filtering"
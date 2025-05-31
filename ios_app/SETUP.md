# iOS App Setup Instructions

## Opening in Xcode

1. Navigate to the `ios_app` directory
2. Double-click `RuckusZTP.xcodeproj` to open in Xcode
3. Select your development team in the project settings (if needed)
4. Choose a simulator or connected device from the scheme selector
5. Click the Run button (▶️) to build and run

## Configuration

Before running the app, update the server configuration:

1. Open `RuckusZTP/Models/Config.swift`
2. Update the `baseURL` and `wsURL` to point to your backend server:
   ```swift
   static let baseURL = "http://your-server-ip:8080"
   static let wsURL = "ws://your-server-ip:8080/ws"
   ```

## Building from Command Line

If you prefer to build from the command line:

```bash
cd ios_app
./build.sh
```

Note: This requires Xcode to be installed (not just Command Line Tools).

## Running on Device

To run on a physical iPhone:

1. Connect your iPhone via USB
2. Select your device from the scheme selector in Xcode
3. You may need to trust the developer certificate on your iPhone:
   - Go to Settings > General > Device Management
   - Trust your developer certificate

## Features

The iOS app provides complete feature parity with the web interface:

- **Configuration**: Manage all ZTP settings
- **Monitoring**: Real-time device status
- **Topology**: Visual network map
- **AI Agent**: Natural language network management
- **Logs**: System log viewer

## Troubleshooting

If you encounter build errors:

1. Ensure you have Xcode 14+ installed
2. Clean the build folder: Product > Clean Build Folder
3. Delete derived data if needed
4. Ensure the backend server is running and accessible
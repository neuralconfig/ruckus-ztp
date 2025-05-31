import SwiftUI

@main
struct RuckusZTPApp: App {
    @StateObject private var networkManager = NetworkManager()
    @StateObject private var configManager = ConfigurationManager()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(networkManager)
                .environmentObject(configManager)
        }
    }
}
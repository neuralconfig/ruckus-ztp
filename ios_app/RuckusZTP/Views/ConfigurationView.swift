import SwiftUI

struct ConfigurationView: View {
    @EnvironmentObject var configManager: ConfigurationManager
    @EnvironmentObject var networkManager: NetworkManager
    @State private var showingAddCredential = false
    @State private var showingAddSeedSwitch = false
    @State private var showingSaveAlert = false
    @State private var saveError: String?
    
    var body: some View {
        NavigationView {
            Form {
                // Credentials Section
                Section(header: Text("Credentials")) {
                    ForEach(Array(configManager.credentials.enumerated()), id: \.element.id) { index, credential in
                        HStack {
                            Text("\(credential.username) / \(credential.password)")
                                .font(.system(.body, design: .monospaced))
                            Spacer()
                            if index > 0 {
                                Button(action: {
                                    configManager.removeCredential(at: index)
                                }) {
                                    Image(systemName: "trash")
                                        .foregroundColor(.red)
                                }
                            } else {
                                Text("(default)")
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                    
                    Button(action: { showingAddCredential = true }) {
                        Label("Add Credential", systemImage: "plus.circle")
                    }
                    
                    TextField("New super password", text: $configManager.preferredPassword)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                }
                
                // Seed Switches Section
                Section(header: Text("Seed Switches")) {
                    ForEach(Array(configManager.seedSwitches.enumerated()), id: \.element.id) { index, seedSwitch in
                        HStack {
                            Text(seedSwitch.ip)
                                .font(.system(.body, design: .monospaced))
                            Spacer()
                            Button(action: {
                                configManager.removeSeedSwitch(at: index)
                            }) {
                                Image(systemName: "trash")
                                    .foregroundColor(.red)
                            }
                        }
                    }
                    
                    Button(action: { showingAddSeedSwitch = true }) {
                        Label("Add Seed Switch", systemImage: "plus.circle")
                    }
                }
                
                // Base Configuration Section
                Section(header: Text("Base Configuration")) {
                    Picker("Configuration", selection: $configManager.baseConfigName) {
                        ForEach(Array(configManager.baseConfigs.keys.sorted()), id: \.self) { name in
                            Text(name).tag(name)
                        }
                    }
                    
                    if let content = configManager.baseConfigs[configManager.baseConfigName] {
                        Text("Preview:")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text(String(content.prefix(200)) + (content.count > 200 ? "..." : ""))
                            .font(.system(.caption, design: .monospaced))
                            .padding(8)
                            .background(Color(.systemGray6))
                            .cornerRadius(8)
                    }
                }
                
                // AI Agent Settings Section
                Section(header: Text("AI Agent Settings")) {
                    TextField("OpenRouter API Key", text: $configManager.openrouterApiKey)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    
                    Picker("Model", selection: $configManager.selectedModel) {
                        Text("Claude 3.5 Haiku").tag("anthropic/claude-3-5-haiku")
                        Text("Claude 3.5 Sonnet").tag("anthropic/claude-3-5-sonnet")
                        Text("GPT-4").tag("openai/gpt-4")
                        Text("GPT-3.5 Turbo").tag("openai/gpt-3.5-turbo")
                    }
                }
                
                // Network Settings Section
                Section(header: Text("Network Settings")) {
                    HStack {
                        Text("Management VLAN")
                        Spacer()
                        TextField("VLAN", value: $configManager.managementVlan, formatter: NumberFormatter())
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .frame(width: 80)
                            .multilineTextAlignment(.trailing)
                    }
                    
                    HStack {
                        Text("Wireless VLANs")
                        Spacer()
                        TextField("20,30,40", text: $configManager.wirelessVlans)
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .frame(width: 120)
                            .multilineTextAlignment(.trailing)
                    }
                    
                    TextField("IP Pool", text: $configManager.ipPool)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    
                    TextField("Gateway", text: $configManager.gateway)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    
                    TextField("DNS Server", text: $configManager.dnsServer)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    
                    HStack {
                        Text("Poll Interval (seconds)")
                        Spacer()
                        TextField("60", value: $configManager.pollInterval, formatter: NumberFormatter())
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .frame(width: 80)
                            .multilineTextAlignment(.trailing)
                    }
                }
                
                // Action Buttons
                Section {
                    Button(action: saveConfiguration) {
                        HStack {
                            Image(systemName: "square.and.arrow.down")
                            Text("Save Configuration")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(BorderedProminentButtonStyle())
                    
                    Button(action: {
                        Task {
                            if networkManager.ztpStatus.running {
                                await networkManager.stopZTP()
                            } else {
                                await networkManager.startZTP()
                            }
                        }
                    }) {
                        HStack {
                            Image(systemName: networkManager.ztpStatus.running ? "stop.circle" : "play.circle")
                            Text(networkManager.ztpStatus.running ? "Stop ZTP Process" : "Start ZTP Process")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(BorderedProminentButtonStyle())
                    .tint(networkManager.ztpStatus.running ? .red : .green)
                }
            }
            .navigationTitle("RUCKUS ZTP Agent")
            .sheet(isPresented: $showingAddCredential) {
                AddCredentialView { credential in
                    configManager.addCredential(credential)
                }
            }
            .sheet(isPresented: $showingAddSeedSwitch) {
                AddSeedSwitchView { seedSwitch in
                    configManager.addSeedSwitch(seedSwitch)
                }
            }
            .alert("Configuration Saved", isPresented: $showingSaveAlert) {
                Button("OK", role: .cancel) { }
            } message: {
                if let error = saveError {
                    Text("Error: \(error)")
                } else {
                    Text("Configuration has been saved successfully.")
                }
            }
        }
    }
    
    private func saveConfiguration() {
        Task {
            do {
                try await configManager.saveConfiguration()
                saveError = nil
                showingSaveAlert = true
            } catch {
                saveError = error.localizedDescription
                showingSaveAlert = true
            }
        }
    }
}

// MARK: - Add Credential View
struct AddCredentialView: View {
    @Environment(\.dismiss) var dismiss
    @State private var username = ""
    @State private var password = ""
    let onSave: (CredentialPair) -> Void
    
    var body: some View {
        NavigationView {
            Form {
                TextField("Username", text: $username)
                TextField("Password", text: $password)
            }
            .navigationTitle("Add Credential")
            .navigationBarItems(
                leading: Button("Cancel") { dismiss() },
                trailing: Button("Save") {
                    onSave(CredentialPair(username: username, password: password))
                    dismiss()
                }
                .disabled(username.isEmpty || password.isEmpty)
            )
        }
    }
}

// MARK: - Add Seed Switch View
struct AddSeedSwitchView: View {
    @Environment(\.dismiss) var dismiss
    @State private var ipAddress = ""
    let onSave: (SeedSwitch) -> Void
    
    var body: some View {
        NavigationView {
            Form {
                TextField("IP Address", text: $ipAddress)
                    .keyboardType(.numbersAndPunctuation)
            }
            .navigationTitle("Add Seed Switch")
            .navigationBarItems(
                leading: Button("Cancel") { dismiss() },
                trailing: Button("Save") {
                    onSave(SeedSwitch(ip: ipAddress, credentialsId: nil))
                    dismiss()
                }
                .disabled(ipAddress.isEmpty)
            )
        }
    }
}

struct ConfigurationView_Previews: PreviewProvider {
    static var previews: some View {
        ConfigurationView()
            .environmentObject(ConfigurationManager())
            .environmentObject(NetworkManager())
    }
}
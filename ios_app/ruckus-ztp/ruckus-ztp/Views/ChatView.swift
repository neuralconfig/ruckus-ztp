import SwiftUI

struct ChatView: View {
    @State private var messages: [ChatMessageView] = [
        ChatMessageView(
            id: UUID(),
            content: """
            Hello! I'm your AI assistant for network operations. I have access to tools to help manage your network:
            
            🔍 Discovery & Status Tools:
            • get_network_summary - Network overview
            • get_switches - List all switches
            • get_switch_details - Detailed switch info
            • get_ztp_status - ZTP process status
            • get_ap_inventory - View access points
            • get_lldp_neighbors - Show LLDP neighbors
            
            🔧 Port Management Tools:
            • get_port_status - Check port status
            • change_port_vlan - Assign port to VLAN
            • set_port_status - Enable/disable port
            • set_poe_status - Control PoE power
            
            📋 Diagnostic Tools:
            • run_show_command - Execute show commands
            
            Example requests:
            • "Show me all switches in the network"
            • "What's the status of port 1/1/7 on switch 192.168.1.100?"
            • "Change port 1/1/5 to VLAN 30 on the main switch"
            
            What would you like to know or configure?
            """,
            isUser: false,
            timestamp: Date()
        )
    ]
    @State private var inputText = ""
    @State private var isLoading = false
    @EnvironmentObject var configManager: ConfigurationManager
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Messages
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(messages) { message in
                                MessageBubble(message: message)
                                    .id(message.id)
                            }
                            
                            if isLoading {
                                HStack {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle())
                                        .scaleEffect(0.8)
                                    Text("AI is thinking...")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                                .padding()
                            }
                        }
                        .padding()
                    }
                    .onChange(of: messages.count) { _ in
                        withAnimation {
                            proxy.scrollTo(messages.last?.id, anchor: .bottom)
                        }
                    }
                }
                
                Divider()
                
                // Input area
                HStack(spacing: 12) {
                    TextField("Ask me anything about your network...", text: $inputText)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                        .onSubmit {
                            sendMessage()
                        }
                    
                    Button(action: sendMessage) {
                        Image(systemName: "paperplane.fill")
                    }
                    .buttonStyle(BorderedProminentButtonStyle())
                    .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isLoading)
                }
                .padding()
            }
            .navigationTitle("AI Agent")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Menu {
                        Button(action: clearChat) {
                            Label("Clear Chat", systemImage: "trash")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
        }
    }
    
    private func sendMessage() {
        let message = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty else { return }
        
        // Add user message
        messages.append(ChatMessageView(
            id: UUID(),
            content: message,
            isUser: true,
            timestamp: Date()
        ))
        
        inputText = ""
        isLoading = true
        
        // Send to API
        Task {
            await sendChatMessage(message)
        }
    }
    
    @MainActor
    private func sendChatMessage(_ message: String) async {
        defer { isLoading = false }
        
        guard let url = URL(string: "\(Config.baseURL)/api/chat") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let chatMessage = ChatMessage(message: message)
        
        do {
            request.httpBody = try JSONEncoder().encode(chatMessage)
            let (data, _) = try await URLSession.shared.data(for: request)
            let response = try JSONDecoder().decode(ChatResponse.self, from: data)
            
            messages.append(ChatMessageView(
                id: UUID(),
                content: response.response,
                isUser: false,
                timestamp: Date()
            ))
        } catch {
            messages.append(ChatMessageView(
                id: UUID(),
                content: "Error: Failed to get response from AI. Please check your API key and connection.",
                isUser: false,
                timestamp: Date(),
                isError: true
            ))
        }
    }
    
    private func clearChat() {
        messages = [messages.first!] // Keep the initial message
    }
}

// MARK: - Chat Message View Model
struct ChatMessageView: Identifiable {
    let id: UUID
    let content: String
    let isUser: Bool
    let timestamp: Date
    var isError: Bool = false
}

// MARK: - Message Bubble
struct MessageBubble: View {
    let message: ChatMessageView
    
    var body: some View {
        HStack {
            if message.isUser {
                Spacer(minLength: 60)
            }
            
            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 4) {
                Text(message.content)
                    .padding(12)
                    .background(
                        message.isError ? Color.red.opacity(0.1) :
                        message.isUser ? Color.blue : Color(.systemGray5)
                    )
                    .foregroundColor(
                        message.isError ? .red :
                        message.isUser ? .white : .primary
                    )
                    .cornerRadius(16)
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(
                                message.isError ? Color.red.opacity(0.3) : Color.clear,
                                lineWidth: 1
                            )
                    )
                
                Text(message.timestamp, style: .time)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            
            if !message.isUser {
                Spacer(minLength: 60)
            }
        }
    }
}

struct ChatView_Previews: PreviewProvider {
    static var previews: some View {
        ChatView()
            .environmentObject(ConfigurationManager())
    }
}
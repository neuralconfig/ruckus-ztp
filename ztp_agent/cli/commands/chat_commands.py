"""
Chat interface commands for CLI.
"""
from cmd2 import with_category

# Define command categories
CMD_CATEGORY_CHAT = "Chat Interface Commands"


class ChatCommandsMixin:
    """Chat interface commands for CLI"""
    
    #
    # Chat Interface Commands
    #
    @with_category(CMD_CATEGORY_CHAT)
    def do_chat(self, _):
        """Enter chat interface with AI agent"""
        self.poutput("\nEntering chat interface. Type 'exit' to return to CLI.")
        
        # Simple chat loop
        while True:
            user_input = input("You: ")
            if user_input.lower() in ('exit', 'quit'):
                break
                
            # Here you would pass the input to your agent
            # For now, just echo back
            print(f"Agent: I received: {user_input}")
        
        self.poutput("Exiting chat interface\n")
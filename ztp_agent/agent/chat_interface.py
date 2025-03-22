"""
Chat interface module that integrates the AI agent with the CLI
"""
import logging
from typing import Dict, List, Optional, Any

# Import your agent components
from smolagents import ToolCallingAgent as Agent
from smolagents import OpenAIServerModel

from ztp_agent.network.switch import SwitchOperation
from ztp_agent.agent.tools import get_network_tools

# Set up logging
logger = logging.getLogger(__name__)

class ChatInterface:
    """Chat interface that integrates the AI agent with the CLI"""
    
    def __init__(
        self,
        openrouter_api_key: str,
        model: str,
        switches: Dict[str, Any]
    ):
        """
        Initialize the chat interface.
        
        Args:
            openrouter_api_key: OpenRouter API key.
            model: OpenRouter model to use.
            switches: Dictionary of switch information.
        """
        self.openrouter_api_key = openrouter_api_key
        self.model = model
        self.switches = switches
        
        # Set up the AI agent
        self.agent = self._create_agent()
        
        logger.info(f"Initialized chat interface with model: {model}")
    
    def _create_agent(self) -> Agent:
        """
        Create an AI agent with network tools.
        
        Returns:
            Agent instance.
        """
        # Convert your switch dictionary to SwitchOperation instances
        switch_operations = self._prepare_switch_operations()
        
        # Get tools for the agent
        tools = get_network_tools(switch_operations)
        
        # Set up the system message for the agent
        system_message = """
        You are a network assistant that helps configure and manage RUCKUS network devices.
        
        You can perform the following tasks:
        1. Change VLAN on a port
        2. Enable or disable a port
        3. Enable or disable PoE on a port
        
        When given a request, analyze it to determine the appropriate action.
        Provide clear, concise responses explaining what configuration changes you've made.
        """
        
        # Create prompt templates
        from smolagents import PromptTemplates
        import yaml
        import importlib
        
        # Get default templates
        default_templates = yaml.safe_load(
            importlib.resources.files("smolagents.prompts").joinpath("toolcalling_agent.yaml").read_text()
        )
        
        # Create custom prompt templates with our system message
        prompt_templates = PromptTemplates(
            system_prompt=system_message,
            planning=default_templates["planning"],
            managed_agent=default_templates["managed_agent"],
            final_answer=default_templates["final_answer"]
        )
        
        # Configure client settings for OpenRouter
        client_kwargs = {
            "default_headers": {
                "HTTP-Referer": "http://localhost:8000",  # Required by OpenRouter
                "X-Title": "ZTP Network Agent"  # Optional app name
            }
        }
        
        # Create and return the agent
        agent = Agent(
            tools=tools, 
            model=OpenAIServerModel(
                model_id=self.model,
                api_key=self.openrouter_api_key,
                api_base="https://openrouter.ai/api/v1",
                client_kwargs=client_kwargs
            ),
            prompt_templates=prompt_templates
        )
        
        return agent
    
    def _prepare_switch_operations(self) -> Dict[str, SwitchOperation]:
        """
        Convert switch dictionary to SwitchOperation instances.
        
        Returns:
            Dictionary of switch name to SwitchOperation instance.
        """
        switch_operations = {}
        for ip, switch_info in self.switches.items():
            # Create a SwitchOperation instance for each switch
            switch_operations[ip] = SwitchOperation(
                ip=ip,
                username=switch_info.get('username'),
                password=switch_info.get('password')
            )
        
        return switch_operations
    
    def process_message(self, message: str) -> str:
        """
        Process a message through the AI agent.
        
        Args:
            message: User message.
            
        Returns:
            Agent's response.
        """
        try:
            logger.debug(f"Processing message through agent: {message}")
            response = self.agent.run(message)
            logger.debug(f"Agent response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error processing message through agent: {e}", exc_info=True)
            return f"Error: {str(e)}"
    
    def run_interactive(self):
        """
        Run an interactive chat session.
        
        Returns when the user types 'exit' or 'quit'.
        """
        print("\nEntering chat interface with network agent. Type 'exit' to return to CLI.")
        print("You can ask the agent to perform network operations like changing VLANs or port status.")
        
        while True:
            try:
                # Get user input
                user_input = input("\nYou: ").strip()
                
                # Check for exit command
                if user_input.lower() in ('exit', 'quit'):
                    print("Exiting chat interface")
                    break
                
                # Process through agent
                if user_input:
                    response = self.process_message(user_input)
                    print(f"\nAgent: {response}")
                
            except KeyboardInterrupt:
                print("\nReceived keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"Error in chat loop: {e}", exc_info=True)
                print(f"\nError: {str(e)}")

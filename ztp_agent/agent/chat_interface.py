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
        switches: Dict[str, Any],
        ztp_process = None
    ):
        """
        Initialize the chat interface.
        
        Args:
            openrouter_api_key: OpenRouter API key.
            model: OpenRouter model to use.
            switches: Dictionary of switch information.
            ztp_process: ZTP process instance for accessing inventory.
        """
        self.openrouter_api_key = openrouter_api_key
        self.model = model
        self.switches = switches
        self.ztp_process = ztp_process
        
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
        tools = get_network_tools(switch_operations, self.ztp_process)
        
        # Set up the system message for the agent
        system_message = """
        You are a network assistant specialized in RUCKUS ICX FastIron switches and Zero-Touch Provisioning (ZTP).
        You help configure and manage network devices in a ZTP environment.
        
        TOOL SELECTION GUIDELINES:
        - For ZTP-related questions ("is ZTP running?", "ZTP status", "ZTP process"): Use get_ztp_status FIRST
        - For access point questions ("AP status", "access points"): Use get_ap_inventory  
        - For switch discovery ("list switches", "available switches"): Use get_switches first
        - For port operations: Always get_port_status before making changes
        - For network topology: Use get_lldp_neighbors
        - For detailed diagnostics: Use run_show_command with appropriate ICX commands
        - For general network overview: Use get_network_summary
        
        CRITICAL: When user asks about "ZTP" or "Zero Touch Provisioning", always use get_ztp_status NOT get_switches!
        
        AVAILABLE TOOLS BY CATEGORY:
        
        🔍 DISCOVERY & STATUS:
        - get_switches: List all managed switches (use this first for switch operations)
        - get_ztp_status: ZTP process status, statistics, configuration details
        - get_ap_inventory: Access point inventory and connection details
        - get_lldp_neighbors: Network topology and neighbor discovery
        
        🔧 PORT MANAGEMENT:
        - get_port_status: Check port status, VLAN, PoE (use before changes)
        - change_port_vlan: Modify port VLAN assignment
        - set_port_status: Enable/disable ports
        - set_poe_status: Control PoE power delivery
        
        📋 DIAGNOSTICS:
        - run_show_command: Execute ICX CLI commands (show version, show interfaces brief, 
          show running-config, show vlan, show mac-address, show spanning-tree, etc.)
        
        OPERATION WORKFLOW:
        1. For switch operations: Start with get_switches to see available devices
        2. For port changes: Check current status with get_port_status first
        3. For troubleshooting: Use get_lldp_neighbors and run_show_command
        4. For ZTP questions: Use get_ztp_status (not get_ap_inventory)
        
        RUCKUS ICX CONTEXT:
        - Ports are named as x/y/z format (e.g., 1/1/7, 1/1/8)
        - VLANs range from 1-4094
        - PoE available on supported ports
        
        Always provide clear explanations of what you found and any changes made.
        Verify results when possible and suggest next steps for complex operations.
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
        Gets the latest switch data from ZTP process if available.
        
        Returns:
            Dictionary of switch IP to SwitchOperation instance.
        """
        switch_operations = {}
        
        # Use ZTP process inventory if available (preferred source)
        if self.ztp_process:
            try:
                # ZTP process stores switches keyed by MAC address
                ztp_switches = getattr(self.ztp_process, 'inventory', {}).get('switches', {})
                logger.info(f"Found {len(ztp_switches)} switches in ZTP inventory")
                
                for mac, switch_info in ztp_switches.items():
                    ip = switch_info.get('ip')
                    if not ip:
                        logger.warning(f"Switch {mac} has no IP address in ZTP inventory")
                        continue
                        
                    # Create a SwitchOperation instance for each switch
                    switch_operations[ip] = SwitchOperation(
                        ip=ip,
                        username=switch_info.get('username'),
                        password=switch_info.get('password'),
                        preferred_password=switch_info.get('preferred_password')
                    )
                    logger.debug(f"Added switch {ip} from ZTP inventory")
            except Exception as e:
                logger.error(f"Error accessing ZTP inventory: {e}")
                # Fall back to CLI switches
        
        # If no switches from ZTP, fallback to CLI switches (keyed by IP address)
        if not switch_operations and self.switches:
            logger.info(f"Falling back to CLI switches, found {len(self.switches)} switches")
            for ip, switch_info in self.switches.items():
                # Create a SwitchOperation instance for each switch
                switch_operations[ip] = SwitchOperation(
                    ip=ip,
                    username=switch_info.get('username'),
                    password=switch_info.get('password'),
                    preferred_password=switch_info.get('preferred_password', switch_info.get('password'))
                )
                logger.debug(f"Added switch {ip} from CLI switches")
        
        logger.info(f"Prepared {len(switch_operations)} switch operations for AI agent")
        
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

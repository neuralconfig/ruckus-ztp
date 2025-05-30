"""
LangChain chat interface module that integrates the AI agent with the CLI
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from typing import Iterator, Any

from ztp_agent.network.switch import SwitchOperation
from ztp_agent.agent.simple_langchain_tools import get_network_tools

# Set up logging
logger = logging.getLogger(__name__)

class StreamingAgentCallback(BaseCallbackHandler):
    """Callback that captures and streams agent steps in real-time."""
    
    def __init__(self, stream_callback=None):
        self.stream_callback = stream_callback  # Function to call with each step
        self.current_reasoning = ""
    
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """Called when LLM starts generating."""
        logger.debug("StreamingAgentCallback: on_llm_start called")
        if self.stream_callback:
            logger.debug("StreamingAgentCallback: Sending thinking message")
            self.stream_callback("thinking", "Thinking...")
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Called when a new token is generated."""
        self.current_reasoning += token
    
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """Called when a tool starts executing."""
        tool_name = serialized.get("name", "Unknown Tool")
        logger.debug(f"StreamingAgentCallback: on_tool_start called for {tool_name}")
        
        # Send any accumulated reasoning first
        if self.current_reasoning.strip():
            reasoning = self.current_reasoning.strip()
            if len(reasoning) > 20:
                if self.stream_callback:
                    logger.debug(f"StreamingAgentCallback: Sending responded message: {reasoning[:50]}...")
                    self.stream_callback("responded", f"responded: {reasoning}")
            self.current_reasoning = ""
        
        # Send the tool invocation
        try:
            import json
            if input_str.startswith('{'):
                parsed_input = json.loads(input_str)
                invoking_msg = f"Invoking: `{tool_name}` with `{json.dumps(parsed_input)}`"
            else:
                invoking_msg = f"Invoking: `{tool_name}` with `{input_str}`"
        except:
            invoking_msg = f"Invoking: `{tool_name}`"
        
        if self.stream_callback:
            logger.debug(f"StreamingAgentCallback: Sending invoking message: {invoking_msg}")
            self.stream_callback("invoking", invoking_msg)
    
    def on_tool_end(self, output: str, **kwargs) -> None:
        """Called when a tool finishes executing."""
        # Send tool result summary
        if output and self.stream_callback:
            summary = self._summarize_tool_output(output)
            if summary:
                self.stream_callback("result", summary)
    
    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM finishes generating."""
        # Send any final reasoning
        if self.current_reasoning.strip():
            reasoning = self.current_reasoning.strip()
            if len(reasoning) > 20:
                if self.stream_callback:
                    self.stream_callback("responded", f"responded: {reasoning}")
            self.current_reasoning = ""
    
    def _summarize_tool_output(self, output: str) -> str:
        """Create a brief summary of tool output."""
        try:
            if isinstance(output, str) and output.strip().startswith('{'):
                import json
                data = json.loads(output)
                
                if isinstance(data, dict):
                    if data.get('success') == True:
                        return "Command executed successfully"
                    elif data.get('success') == False:
                        return f"Command failed: {data.get('error', 'Unknown error')}"
                    elif 'running' in data:
                        running = data.get('running', False)
                        switches = data.get('switches_discovered', 0)
                        aps = data.get('aps_discovered', 0)
                        return f"ZTP is {'running' if running else 'stopped'}, found {switches} switches and {aps} APs"
            
            if len(str(output)) > 100:
                return f"Received {len(str(output))} characters of data"
            
            return None
        except Exception:
            return None

class StreamingChatOpenAI(ChatOpenAI):
    """A wrapper around ChatOpenAI with enhanced error handling for streaming."""
    
    def __init__(self, *args, **kwargs):
        # Enable streaming by default for better UX
        kwargs.setdefault('streaming', True)
        super().__init__(*args, **kwargs)

class LangChainChatInterface:
    """LangChain chat interface that integrates the AI agent with the CLI"""
    
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
        self.agent_executor = self._create_agent()
        
        logger.info(f"Initialized LangChain chat interface with model: {model}")
    
    def _create_agent(self) -> AgentExecutor:
        """
        Create a LangChain AI agent with network tools.
        
        Returns:
            AgentExecutor instance.
        """
        # Convert your switch dictionary to SwitchOperation instances
        switch_operations = self._prepare_switch_operations()
        
        # Get tools for the agent
        tools = get_network_tools(switch_operations, self.ztp_process)
        
        # Set up the system message for the agent
        system_message = """
        You are a network assistant specialized in RUCKUS ICX FastIron switches and Zero-Touch Provisioning (ZTP).
        You help configure and manage network devices in a ZTP environment.
        
        IMPORTANT: You have access to tools that you should use to answer questions and perform operations.
        Think step by step about which tool(s) would best help answer the user's question.
        
        AVAILABLE TOOLS:
        
        🔍 DISCOVERY & STATUS:
        - get_switches: List all managed switches in the network
        - get_ztp_status: Get ZTP process status, statistics, and configuration details
        - get_ap_inventory: Get access point inventory and connection details
        - get_lldp_neighbors: Discover network topology and neighbor connections
        - get_network_summary: Get comprehensive overview of the entire network
        - get_switch_details: Get detailed information about a specific switch (hostname, model, ports)
        
        🔧 PORT MANAGEMENT:
        - get_port_status: Check port status, VLAN assignment, and PoE state
        - change_port_vlan: Modify port VLAN assignment
        - set_port_status: Enable or disable ports
        - set_poe_status: Control PoE power delivery on ports
        
        📋 DIAGNOSTICS:
        - run_show_command: Execute diagnostic 'show' commands on switches (e.g., show interfaces brief, 
          show version, show running-config, show vlan, show mac-address, show log)
        
        APPROACH:
        1. Analyze the user's question to understand what information they need
        2. Select the most appropriate tool(s) to gather that information
        3. If multiple tools might be needed, start with the most general one
        4. Use the tool results to provide a complete and accurate answer
        
        EXAMPLES:
        - "Are there any interface errors on switch X?" → Use run_show_command with "show interfaces brief"
        - "What VLANs are configured?" → Use run_show_command with "show vlan"
        - "Is ZTP running?" → Use get_ztp_status
        - "What switches are available?" → Use get_switches
        - "Show me the network topology" → Use get_lldp_neighbors or get_network_summary
        
        RUCKUS ICX CONTEXT:
        - Ports use x/y/z format (e.g., 1/1/7)
        - VLANs range from 1-4094
        - Common commands: show interfaces brief, show version, show vlan, show running-config
        
        Always provide clear, concise answers based on the actual tool results.
        """
        
        # Create the prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        # Configure LLM for OpenRouter with streaming enabled for better UX
        llm = StreamingChatOpenAI(
            model=self.model,
            api_key=self.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "http://localhost:8000",  # Required by OpenRouter
                "X-Title": "ZTP Network Agent"  # Optional app name
            },
            streaming=True,   # Enable streaming for better user experience
            max_retries=2,    # Allow retries for better reliability
            timeout=60,       # Reasonable timeout
            temperature=0.1,
            top_p=0.9
        )
        
        # Create the agent
        agent = create_tool_calling_agent(llm, tools, prompt)
        
        # Create the agent executor with intermediate steps
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=10,      # Prevent infinite loops
            max_execution_time=120, # 2 minute timeout for safety
            return_intermediate_steps=True  # Enable intermediate steps
        )
        
        return agent_executor
    
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
    
    def process_message_with_streaming(self, message: str, stream_callback=None) -> str:
        """
        Process a message through the AI agent with real-time streaming.
        
        Args:
            message: User message.
            stream_callback: Function to call with each step (step_type, content).
            
        Returns:
            Final agent response.
        """
        try:
            logger.info(f"Processing message with streaming: {message}")
            
            # Send initial message
            if stream_callback:
                stream_callback("thinking", "Processing your request...")
            
            # Implement manual step-by-step execution for true real-time streaming
            return self._execute_agent_with_manual_streaming(message, stream_callback)
            
        except Exception as e:
            logger.error(f"Error in streaming message processing: {e}", exc_info=True)
            if stream_callback:
                stream_callback("error", str(e))
            raise
    
    async def process_message_with_async_streaming(self, message: str, async_stream_callback=None) -> str:
        """
        Process a message through the AI agent with async real-time streaming.
        
        Args:
            message: User message.
            async_stream_callback: Async function to call with each step (step_type, content).
            
        Returns:
            Final agent response.
        """
        try:
            logger.info(f"Processing message with async streaming: {message}")
            
            # Send initial message
            if async_stream_callback:
                await async_stream_callback("thinking", "Processing your request...")
            
            # Implement manual step-by-step execution for true real-time streaming
            return await self._execute_agent_with_async_streaming(message, async_stream_callback)
            
        except Exception as e:
            logger.error(f"Error in async streaming message processing: {e}", exc_info=True)
            if async_stream_callback:
                await async_stream_callback("error", str(e))
            raise
    
    async def _execute_agent_with_async_streaming(self, message: str, async_stream_callback=None) -> str:
        """Execute the agent with async real-time streaming using proper LangChain callbacks."""
        from langchain_core.callbacks import AsyncCallbackHandler
        from typing import Any, Dict, List, Optional, Union
        from uuid import UUID
        import asyncio
        
        class AsyncStreamingCallback(AsyncCallbackHandler):
            """Async callback handler for streaming agent execution."""
            
            def __init__(self, stream_callback):
                self.stream_callback = stream_callback
                self.current_reasoning = ""
                self.tool_inputs = {}
            
            async def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
                """Called when LLM starts."""
                if self.stream_callback:
                    await self.stream_callback("thinking", "Thinking...")
            
            async def on_llm_new_token(self, token: str, **kwargs) -> None:
                """Called on each new token from LLM."""
                self.current_reasoning += token
                
                # Stream reasoning in real-time as it's generated  
                if self.stream_callback and len(self.current_reasoning) > 50:
                    # Check if we have a complete thought (ends with period, question mark, etc.)
                    if any(self.current_reasoning.rstrip().endswith(p) for p in ['.', '?', '!', ':', '\n']):
                        reasoning = self.current_reasoning.strip()
                        if reasoning and not reasoning.startswith('{'):  # Skip JSON-like content
                            await self.stream_callback("thinking", reasoning)
                        self.current_reasoning = ""
            
            async def on_llm_end(self, response: Any, **kwargs) -> None:
                """Called when LLM ends."""
                # Don't send anything here - let the final answer come through the direct return path
                # This prevents duplication of the final reasoning
                self.current_reasoning = ""
            
            async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
                """Called when tool starts."""
                tool_name = serialized.get("name", "Unknown")
                
                if self.stream_callback:
                    # Parse tool input - handle both string and dict inputs
                    try:
                        import json
                        
                        # Handle different input formats
                        if isinstance(input_str, dict):
                            tool_input = input_str
                        elif isinstance(input_str, str):
                            if input_str.strip().startswith('{'):
                                tool_input = json.loads(input_str)
                            else:
                                # Try to parse as a simple parameter string
                                tool_input = {"input": input_str}
                        else:
                            tool_input = {}
                        
                        self.tool_inputs[tool_name] = tool_input
                        
                        # Format the invocation message with parameters
                        if tool_input:
                            params_list = []
                            for k, v in tool_input.items():
                                if isinstance(v, str) and len(v) > 50:
                                    params_list.append(f"{k}='{v[:50]}...'")
                                else:
                                    params_list.append(f"{k}='{v}'")
                            params_str = ", ".join(params_list)
                            await self.stream_callback("invoking", f"Invoking: `{tool_name}` with {params_str}")
                        else:
                            await self.stream_callback("invoking", f"Invoking: `{tool_name}`")
                    except Exception as e:
                        # Log the error for debugging
                        logger.debug(f"Error parsing tool input: {e}, input_str type: {type(input_str)}, value: {input_str}")
                        await self.stream_callback("invoking", f"Invoking: `{tool_name}`")
            
            async def on_tool_end(self, output: str, **kwargs) -> None:
                """Called when tool ends."""
                if self.stream_callback and output:
                    # Create summary of tool output
                    summary = self._summarize_output(output)
                    if summary:
                        await self.stream_callback("result", summary)
            
            def _summarize_output(self, output: str) -> Optional[str]:
                """Summarize tool output."""
                try:
                    if isinstance(output, str) and output.strip().startswith('{'):
                        import json
                        data = json.loads(output)
                        
                        if isinstance(data, dict):
                            if 'success' in data:
                                if data['success']:
                                    return "Tool executed successfully"
                                else:
                                    return f"Tool failed: {data.get('error', 'Unknown error')}"
                            elif 'running' in data:
                                running = data.get('running', False)
                                switches = data.get('switches_discovered', 0)
                                aps = data.get('aps_discovered', 0)
                                return f"ZTP is {'running' if running else 'stopped'}, found {switches} switches and {aps} APs"
                        elif isinstance(data, list):
                            return f"Found {len(data)} items"
                    
                    if len(str(output)) > 100:
                        return f"Received {len(str(output))} characters of output"
                    
                    return None
                except:
                    return None
        
        try:
            # Send initial thinking message
            if async_stream_callback:
                await async_stream_callback("thinking", "Processing your request...")
            
            # Create async callback
            callback = AsyncStreamingCallback(async_stream_callback)
            
            # Execute agent with callback
            response = await self.agent_executor.ainvoke(
                {"input": message},
                config={"callbacks": [callback]}
            )
            
            # Log the raw response for debugging
            logger.info(f"Agent response type: {type(response)}, keys: {response.keys() if isinstance(response, dict) else 'N/A'}")
            
            # Extract and return the final answer (will be sent with proper "final" styling)
            final_answer = response.get("output", "No response generated")
            
            # Log the final answer for debugging
            logger.info(f"Returning final answer: {len(final_answer)} chars, preview: {final_answer[:100]}...")
            
            return final_answer
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error in agent execution: {error_msg}", exc_info=True)
            
            # Check if this is the asyncio error
            if "cannot access local variable 'asyncio'" in error_msg:
                logger.error("Asyncio scope error detected - this suggests a problem with variable scoping in callbacks")
                # Don't send the confusing asyncio error to the user
                error_msg = "An error occurred while processing your request. Please try again."
            
            if async_stream_callback:
                try:
                    await async_stream_callback("error", error_msg)
                except Exception as callback_error:
                    logger.error(f"Failed to send error via callback: {callback_error}")
            
            return f"Sorry, I encountered an error: {error_msg}"
    
    def _explain_tool_selection(self, tool_name: str, message: str) -> str:
        """Explain why a particular tool was selected."""
        message_lower = message.lower()
        
        explanations = {
            "run_show_command": f"Detected IP address and keywords like 'interface', 'error', 'show', or 'config' in your message. This tool can execute diagnostic commands on switches.",
            "get_switch_details": f"Found IP address with request for details/info. This tool provides comprehensive switch information.",
            "get_ztp_status": f"Detected ZTP-related keywords like 'ztp', 'status', 'running'. This tool shows Zero Touch Provisioning status.",
            "get_switches": f"Request mentions switches/devices. This tool lists all available switches in the network.",
            "get_ap_inventory": f"Detected access point keywords like 'ap', 'access point', 'wireless'. This tool shows AP inventory.",
            "get_network_summary": f"Request for summary/overview. This tool provides comprehensive network status.",
            "get_lldp_neighbors": f"Request for topology/neighbor information. This tool discovers network connections."
        }
        
        return explanations.get(tool_name, f"Selected based on message analysis and keyword matching.")
    
    def _analyze_request(self, message: str) -> str:
        """Analyze the user request and return detailed analysis."""
        message_lower = message.lower()
        analysis_parts = []
        
        # Check for IP addresses
        ip_match = self._extract_switch_ip(message)
        if ip_match:
            analysis_parts.append(f"Found IP address: {ip_match}")
        
        # Check for key operation words
        key_words = []
        if any(word in message_lower for word in ["interface", "port"]):
            key_words.append("interface/port operations")
        if any(word in message_lower for word in ["error", "problem", "issue"]):
            key_words.append("troubleshooting")
        if any(word in message_lower for word in ["show", "display", "get"]):
            key_words.append("information retrieval")
        if any(word in message_lower for word in ["status", "state"]):
            key_words.append("status checking")
        if any(word in message_lower for word in ["ztp", "provisioning"]):
            key_words.append("ZTP operations")
        if any(word in message_lower for word in ["ap", "wireless", "access"]):
            key_words.append("wireless/AP operations")
        
        if key_words:
            analysis_parts.append(f"Operation type: {', '.join(key_words)}")
        
        # Check for specific commands
        if any(word in message_lower for word in ["version", "model"]):
            analysis_parts.append("Requesting device information")
        if any(word in message_lower for word in ["config", "configuration"]):
            analysis_parts.append("Configuration related")
        
        return "; ".join(analysis_parts) if analysis_parts else "General network inquiry"
    
    async def _send_command_details(self, result, async_stream_callback):
        """Send detailed information about command execution."""
        import asyncio
        try:
            if isinstance(result, dict) and result.get('success'):
                output = result.get('output', '')
                command = result.get('command', '')
                switch_ip = result.get('switch_ip', '')
                
                # Show command execution details
                await async_stream_callback("thinking", f"Successfully executed '{command}' on switch {switch_ip}")
                
                # Analyze the output for interesting details
                if 'show interfaces brief' in command.lower():
                    await self._analyze_interface_output(output, async_stream_callback)
                elif 'show version' in command.lower():
                    await self._analyze_version_output(output, async_stream_callback)
                
            elif isinstance(result, dict) and not result.get('success'):
                error = result.get('error', 'Unknown error')
                await async_stream_callback("thinking", f"Command execution failed: {error}")
                
        except Exception as e:
            logger.error(f"Error sending command details: {e}")
    
    async def _analyze_interface_output(self, output, async_stream_callback):
        """Analyze interface command output and provide insights."""
        import asyncio
        try:
            lines = output.split('\n')
            up_count = 0
            down_count = 0
            disabled_count = 0
            
            for line in lines:
                if 'Up' in line and 'Forward' in line:
                    up_count += 1
                elif 'Down' in line:
                    down_count += 1
                elif 'Disabled' in line:
                    disabled_count += 1
            
            if up_count > 0 or down_count > 0 or disabled_count > 0:
                await async_stream_callback("thinking", f"Interface analysis: {up_count} Up, {down_count} Down, {disabled_count} Disabled ports")
                
        except Exception as e:
            logger.error(f"Error analyzing interface output: {e}")
    
    async def _analyze_version_output(self, output, async_stream_callback):
        """Analyze version command output and provide insights."""
        import asyncio
        try:
            lines = output.split('\n')
            for line in lines:
                if 'ICX' in line and ('Switch' in line or 'Router' in line):
                    await async_stream_callback("thinking", f"Device model identified: {line.strip()}")
                    break
                    
        except Exception as e:
            logger.error(f"Error analyzing version output: {e}")
    
    def _execute_agent_with_manual_streaming(self, message: str, stream_callback=None) -> str:
        """Execute the agent manually with real-time streaming."""
        import time
        
        try:
            # Send thinking message
            if stream_callback:
                stream_callback("thinking", "Analyzing your request...")
                time.sleep(0.1)
            
            # Get the tools
            tools = self.agent_executor.tools
            
            # Simple execution loop
            if stream_callback:
                stream_callback("thinking", "Determining which tools to use...")
                time.sleep(0.2)
            
            # Determine which tool to use based on the message content
            tool_to_use = self._determine_tool(message, tools)
            
            if tool_to_use:
                # Send invoking message
                if stream_callback:
                    stream_callback("invoking", f"Invoking: `{tool_to_use.name}`")
                    time.sleep(0.1)
                
                # Execute the tool
                try:
                    # Check if this is a tool that needs parameters
                    if tool_to_use.name == "run_show_command":
                        # Extract switch IP and command from message
                        switch_ip, command = self._parse_show_command_request(message)
                        if switch_ip and command:
                            result = tool_to_use.run({"switch_ip": switch_ip, "command": command})
                        else:
                            result = {"error": "Could not parse switch IP or command from request"}
                    elif tool_to_use.name == "get_switch_details":
                        # Extract switch IP from message
                        switch_ip = self._extract_switch_ip(message)
                        if switch_ip:
                            result = tool_to_use.run({"switch_ip": switch_ip})
                        else:
                            result = {"error": "Could not find switch IP in request"}
                    else:
                        # Tools that don't need parameters
                        result = tool_to_use.run({})
                    
                    # Send result summary
                    if result:
                        summary = self._summarize_tool_output(str(result))
                        if summary and stream_callback:
                            stream_callback("result", summary)
                            time.sleep(0.1)
                    
                    # Generate final response
                    if stream_callback:
                        stream_callback("thinking", "Generating response...")
                        time.sleep(0.1)
                    
                    # Create a response based on the tool result
                    response = self._format_tool_response(tool_to_use.name, result, message)
                    return response
                    
                except Exception as e:
                    if stream_callback:
                        stream_callback("error", f"Tool execution failed: {str(e)}")
                    return f"Sorry, I encountered an error while executing {tool_to_use.name}: {str(e)}"
            
            else:
                # Fallback response
                if stream_callback:
                    stream_callback("thinking", "Generating direct response...")
                    time.sleep(0.1)
                return "I can help you with network operations. Try asking about ZTP status, switches, access points, or specific switch commands."
                
        except Exception as e:
            logger.error(f"Error in manual streaming execution: {e}")
            return f"Sorry, I encountered an error: {str(e)}"
    
    def _determine_tool(self, message: str, tools) -> Any:
        """Determine which tool to use based on the message content."""
        message_lower = message.lower()
        
        # Check for specific IP addresses and show commands
        if any(word in message_lower for word in ["interface", "error", "show", "version", "config"]) and self._extract_switch_ip(message):
            return next((tool for tool in tools if tool.name == "run_show_command"), None)
        elif self._extract_switch_ip(message) and any(word in message_lower for word in ["details", "info", "information"]):
            return next((tool for tool in tools if tool.name == "get_switch_details"), None)
        elif any(word in message_lower for word in ["ztp", "zero", "touch", "provisioning", "status", "running"]):
            return next((tool for tool in tools if tool.name == "get_ztp_status"), None)
        elif any(word in message_lower for word in ["switch", "switches", "device", "devices"]):
            return next((tool for tool in tools if tool.name == "get_switches"), None)
        elif any(word in message_lower for word in ["ap", "access", "point", "wireless"]):
            return next((tool for tool in tools if tool.name == "get_ap_inventory"), None)
        elif any(word in message_lower for word in ["summary", "overview", "network"]):
            return next((tool for tool in tools if tool.name == "get_network_summary"), None)
        
        # Default to ZTP status for most queries
        return next((tool for tool in tools if tool.name == "get_ztp_status"), None)
    
    def _extract_switch_ip(self, message: str) -> str:
        """Extract switch IP address from message."""
        import re
        # Look for IP address pattern
        ip_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
        match = re.search(ip_pattern, message)
        return match.group() if match else None
    
    def _parse_show_command_request(self, message: str):
        """Parse show command request to extract switch IP and command."""
        switch_ip = self._extract_switch_ip(message)
        message_lower = message.lower()
        
        # Determine the show command based on keywords
        if "interface" in message_lower and "error" in message_lower:
            command = "show interfaces brief"
        elif "interface" in message_lower:
            command = "show interfaces brief"
        elif "version" in message_lower:
            command = "show version"
        elif "config" in message_lower:
            command = "show running-config"
        elif "error" in message_lower:
            command = "show log"
        else:
            command = "show interfaces brief"  # Default for interface-related queries
            
        return switch_ip, command
    
    def _format_tool_response(self, tool_name: str, result, original_message: str) -> str:
        """Format response based on tool type and result."""
        if tool_name == "get_ztp_status":
            return self._format_ztp_status_response(result)
        elif tool_name == "get_switches":
            return self._format_switches_response(result)
        elif tool_name == "get_ap_inventory":
            return self._format_ap_response(result)
        elif tool_name == "run_show_command":
            return self._format_show_command_response(result, original_message)
        elif tool_name == "get_switch_details":
            return self._format_switch_details_response(result)
        elif tool_name == "get_network_summary":
            return self._format_network_summary_response(result)
        else:
            return f"Executed {tool_name}:\n\n{str(result)}"
    
    def _format_show_command_response(self, result, original_message: str) -> str:
        """Format show command response."""
        try:
            if isinstance(result, dict):
                if result.get('success'):
                    output = result.get('output', '')
                    command = result.get('command', '')
                    switch_ip = result.get('switch_ip', '')
                    
                    # Check for interface errors specifically
                    if "error" in original_message.lower() and "interface" in original_message.lower():
                        if "down" in output.lower() or "error" in output.lower():
                            return f"Found interface issues on switch {switch_ip}. Some interfaces may be down or have errors. Full output:\n\n{output}"
                        else:
                            return f"No obvious interface errors found on switch {switch_ip}. All interfaces appear to be functioning normally."
                    else:
                        return f"Command '{command}' executed successfully on switch {switch_ip}:\n\n{output}"
                else:
                    error = result.get('error', 'Unknown error')
                    return f"Command failed: {error}"
            else:
                return f"Show command result:\n\n{str(result)}"
        except Exception:
            return f"Show command executed:\n\n{str(result)}"
    
    def _format_switch_details_response(self, result) -> str:
        """Format switch details response."""
        try:
            if isinstance(result, dict):
                if result.get('reachable'):
                    parts = []
                    if result.get('hostname'):
                        parts.append(f"Hostname: {result['hostname']}")
                    if result.get('model'):
                        parts.append(f"Model: {result['model']}")
                    if result.get('version'):
                        parts.append(f"Software: {result['version']}")
                    if result.get('port_count'):
                        parts.append(f"Ports: {result['port_count']}")
                    
                    return f"Switch {result['ip']} details:\n" + "\n".join(parts)
                else:
                    error = result.get('error', 'Switch not reachable')
                    return f"Cannot reach switch {result.get('ip', 'unknown')}: {error}"
            else:
                return f"Switch details:\n\n{str(result)}"
        except Exception:
            return f"Switch details retrieved:\n\n{str(result)}"
    
    def _format_network_summary_response(self, result) -> str:
        """Format network summary response."""
        try:
            if isinstance(result, dict):
                summary_parts = []
                
                # ZTP status
                ztp_status = result.get('ztp_status', {})
                if ztp_status.get('running'):
                    summary_parts.append("✓ ZTP process is running")
                else:
                    summary_parts.append("✗ ZTP process is stopped")
                
                # Switches
                switches = result.get('switches', [])
                reachable = len([s for s in switches if s.get('status') == 'reachable'])
                summary_parts.append(f"Switches: {len(switches)} total, {reachable} reachable")
                
                # Access points
                aps = result.get('access_points', [])
                if aps:
                    configured_aps = len([ap for ap in aps if ap.get('status') == 'Configured'])
                    summary_parts.append(f"Access Points: {len(aps)} total, {configured_aps} configured")
                
                return "Network Summary:\n" + "\n".join(summary_parts)
            else:
                return f"Network summary:\n\n{str(result)}"
        except Exception:
            return f"Network summary retrieved:\n\n{str(result)}"
    
    def _format_ztp_status_response(self, result) -> str:
        """Format ZTP status response."""
        try:
            import json
            if isinstance(result, str):
                data = json.loads(result)
            else:
                data = result
                
            running = data.get('running', False)
            switches = data.get('switches_discovered', 0)
            configured = data.get('switches_configured', 0)
            aps = data.get('aps_discovered', 0)
            
            status_text = "running" if running else "stopped"
            return f"ZTP process is currently {status_text}. Discovered {switches} switches ({configured} configured) and {aps} access points."
            
        except Exception:
            return f"ZTP status retrieved:\n\n{str(result)}"
    
    def _format_switches_response(self, result) -> str:
        """Format switches response."""
        try:
            if isinstance(result, list):
                switches_list = [s.get('ip', 'Unknown') for s in result]
                return f"Found {len(result)} switches in the network: {', '.join(switches_list)}"
            else:
                return f"Switch information:\n\n{str(result)}"
        except Exception:
            return f"Switches retrieved:\n\n{str(result)}"
    
    def _format_ap_response(self, result) -> str:
        """Format AP response."""
        try:
            if isinstance(result, list):
                if result:
                    ap_list = [ap.get('hostname', ap.get('mac', 'Unknown')) for ap in result]
                    return f"Found {len(result)} access points: {', '.join(ap_list)}"
                else:
                    return "No access points discovered yet."
            else:
                return f"Access point information:\n\n{str(result)}"
        except Exception:
            return f"Access points retrieved:\n\n{str(result)}"
    
    def _format_response_with_steps(self, final_response: str, intermediate_steps: List) -> str:
        """Format the response with intermediate steps for better UX."""
        if not intermediate_steps:
            return final_response
        
        formatted_parts = []
        
        for i, (action, observation) in enumerate(intermediate_steps, 1):
            # Extract the log field which contains the "Invoking:" and "responded:" messages
            log = getattr(action, 'log', '')
            
            if log:
                # Parse the log to extract the components
                lines = log.strip().split('\n')
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    if line.startswith('Invoking:'):
                        # Show the invoking message exactly as LangChain generates it
                        formatted_parts.append(f"<div class='agent-invoking'>🔧 {line}</div>")
                    elif line.startswith('responded:'):
                        # Show the responded message exactly as LangChain generates it
                        formatted_parts.append(f"<div class='agent-responded'>💬 {line}</div>")
            
            # Show a summary of the result
            if observation and len(str(observation)) > 0:
                summary = self._summarize_observation(getattr(action, 'tool', 'Unknown'), observation)
                if summary:
                    formatted_parts.append(f"<div class='agent-result'>✅ {summary}</div>")
        
        # Add the final response
        formatted_parts.append(f"<div class='agent-final'>💡 <strong>Final Answer:</strong> {final_response}</div>")
        
        result = "\n\n".join(formatted_parts)
        logger.debug(f"Formatted parts count: {len(formatted_parts)}")
        logger.debug(f"Result contains HTML divs: {result.count('<div')}")
        return result
    
    def _format_response_with_captured_steps(self, final_response: str, captured_steps: List[Dict]) -> str:
        """Format the response with captured reasoning and tool steps."""
        if not captured_steps:
            return final_response
        
        formatted_parts = []
        
        for step in captured_steps:
            if step["type"] == "reasoning":
                # Show the agent's reasoning text
                reasoning = step["content"].strip()
                if reasoning and not reasoning.startswith("I need to") and len(reasoning) > 10:
                    formatted_parts.append(f"<div class='agent-thinking'>💭 {reasoning}</div>")
            
            elif step["type"] == "invoking":
                # Show the "Invoking:" message exactly as it appears in console
                invoking_text = step["content"]
                formatted_parts.append(f"<div class='agent-invoking'>🔧 {invoking_text}</div>")
            
            elif step["type"] == "responded":
                # Show the "responded:" message exactly as it appears in console  
                responded_text = step["content"]
                formatted_parts.append(f"<div class='agent-responded'>💬 {responded_text}</div>")
            
            elif step["type"] == "tool_result":
                # Show summary of tool result
                output = step["output"]
                if output:
                    summary = self._summarize_tool_output(output)
                    if summary:
                        formatted_parts.append(f"<div class='agent-result'>✅ {summary}</div>")
        
        # Add the final response
        formatted_parts.append(f"<div class='agent-final'>💡 <strong>Final Answer:</strong> {final_response}</div>")
        
        return "\n\n".join(formatted_parts)
    
    def _format_response_with_verbose_output(self, final_response: str, verbose_output: str, intermediate_steps: List) -> str:
        """Format the response with captured verbose output and intermediate steps."""
        formatted_parts = []
        
        if verbose_output:
            # Parse the verbose output to extract "Invoking:" and "responded:" lines
            lines = verbose_output.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('Invoking:'):
                    # Format invoking lines
                    formatted_parts.append(f"<div class='agent-invoking'>🔧 {line}</div>")
                elif line.startswith('responded:'):
                    # Format responded lines
                    formatted_parts.append(f"<div class='agent-responded'>💬 {line}</div>")
                elif 'Entering new AgentExecutor chain' in line:
                    formatted_parts.append(f"<div class='agent-thinking'>🚀 Starting agent execution...</div>")
                elif 'Finished chain' in line:
                    formatted_parts.append(f"<div class='agent-thinking'>✨ Agent execution completed</div>")
        
        # Add summaries for intermediate steps if available
        for action, observation in intermediate_steps:
            tool_name = getattr(action, 'tool', 'Unknown Tool')
            summary = self._summarize_tool_output(str(observation))
            if summary:
                formatted_parts.append(f"<div class='agent-result'>✅ {summary}</div>")
        
        # Add the final response
        formatted_parts.append(f"<div class='agent-final'>💡 <strong>Final Answer:</strong> {final_response}</div>")
        
        return "\n\n".join(formatted_parts)
    
    def _summarize_tool_output(self, output: str) -> str:
        """Create a brief summary of tool output."""
        try:
            # Try to parse as JSON
            if isinstance(output, str) and output.strip().startswith('{'):
                import json
                data = json.loads(output)
                
                # Check for common patterns
                if isinstance(data, dict):
                    if data.get('success') == True:
                        return f"Command executed successfully"
                    elif data.get('success') == False:
                        return f"Command failed: {data.get('error', 'Unknown error')}"
                    elif 'running' in data:
                        running = data.get('running', False)
                        switches = data.get('switches_discovered', 0)
                        aps = data.get('aps_discovered', 0)
                        return f"ZTP is {'running' if running else 'stopped'}, found {switches} switches and {aps} APs"
                    elif 'reachable' in data:
                        reachable = data.get('reachable', False)
                        model = data.get('model', 'Unknown model')
                        return f"Switch is {'reachable' if reachable else 'unreachable'}, model: {model}"
                
                elif isinstance(data, list):
                    return f"Found {len(data)} items"
            
            # For non-JSON or simple strings
            if len(str(output)) > 100:
                return f"Received {len(str(output))} characters of data"
            
            return None
            
        except Exception:
            return None
    
    def _describe_action(self, tool_name: str, tool_input: dict) -> str:
        """Create a human-readable description of what action is being taken."""
        descriptions = {
            'get_ztp_status': 'Checking ZTP process status and statistics',
            'get_switches': 'Looking up available switches in the network',
            'get_switch_details': f'Getting detailed information for switch {tool_input.get("switch_ip", "unknown")}',
            'get_port_status': f'Checking status of port {tool_input.get("port", "unknown")} on switch {tool_input.get("switch_ip", "unknown")}',
            'change_port_vlan': f'Changing port {tool_input.get("port", "unknown")} to VLAN {tool_input.get("vlan_id", "unknown")}',
            'set_port_status': f'Setting port {tool_input.get("port", "unknown")} to {tool_input.get("status", "unknown")}',
            'set_poe_status': f'Setting PoE on port {tool_input.get("port", "unknown")} to {tool_input.get("status", "unknown")}',
            'get_lldp_neighbors': f'Discovering network topology for switch {tool_input.get("switch_ip", "unknown")}',
            'run_show_command': f'Running command "{tool_input.get("command", "unknown")}" on switch {tool_input.get("switch_ip", "unknown")}',
            'get_network_summary': 'Getting comprehensive network overview',
            'get_ap_inventory': 'Checking access point inventory'
        }
        
        return descriptions.get(tool_name, f'Using tool {tool_name}')
    
    def _summarize_observation(self, tool_name: str, observation: str) -> str:
        """Create a brief summary of the tool result."""
        try:
            # Try to parse as JSON if it looks like structured data
            if isinstance(observation, dict) or (isinstance(observation, str) and observation.strip().startswith('{')):
                if isinstance(observation, str):
                    import json
                    data = json.loads(observation)
                else:
                    data = observation
                
                # Tool-specific summaries
                if tool_name == 'get_ztp_status':
                    running = data.get('running', False)
                    switches = data.get('switches_discovered', 0)
                    aps = data.get('aps_discovered', 0)
                    return f"ZTP is {'running' if running else 'stopped'}, found {switches} switches and {aps} APs"
                
                elif tool_name == 'get_switches':
                    if isinstance(data, list):
                        return f"Found {len(data)} switches in the network"
                
                elif tool_name == 'get_switch_details':
                    model = data.get('model', 'Unknown model')
                    reachable = data.get('reachable', False)
                    return f"Switch is {'reachable' if reachable else 'unreachable'}, model: {model}"
                
                elif tool_name == 'run_show_command':
                    success = data.get('success', False)
                    if success:
                        output_len = len(data.get('output', ''))
                        return f"Command executed successfully, got {output_len} characters of output"
                    else:
                        return f"Command failed: {data.get('error', 'Unknown error')}"
            
            # For string observations, provide a generic summary
            if isinstance(observation, str) and len(observation) > 100:
                return f"Received {len(observation)} characters of data"
            
            return None  # No summary needed for short responses
            
        except Exception:
            # If we can't parse or summarize, don't show anything
            return None
    
    def process_message(self, message: str) -> str:
        """
        Process a message through the AI agent.
        
        Args:
            message: User message.
            
        Returns:
            Agent's response.
        """
        try:
            logger.debug(f"Processing message through LangChain agent: {message}")
            logger.debug(f"Using model: {self.model}")
            
            # For now, let's focus on fixing the HTML rendering and use intermediate steps
            response = self.agent_executor.invoke({"input": message})
            
            # Extract the final response and intermediate steps
            agent_response = response.get("output", "No response generated")
            intermediate_steps = response.get("intermediate_steps", [])
            
            # Format with intermediate steps  
            formatted_response = self._format_response_with_steps(agent_response, intermediate_steps)
            
            logger.debug(f"LangChain agent response: {agent_response}")
            logger.debug(f"Intermediate steps: {len(intermediate_steps)}")
            logger.debug(f"Formatted response preview: {formatted_response[:200]}...")
            
            return formatted_response
        except Exception as e:
            logger.error(f"Error processing message through LangChain agent: {e}", exc_info=True)
            
            # Check for specific error types and provide helpful messages
            error_str = str(e).lower()
            model_info = f" (Model: {self.model})"
            
            if "internal server error" in error_str:
                return f"I encountered a temporary issue with the AI service{model_info}. This could be due to:\n" \
                       f"• The model may not support function calling properly\n" \
                       f"• Temporary API outage\n" \
                       f"• Model compatibility issues\n\n" \
                       f"Please try switching to Claude 3.5 Haiku or one of the free models in the AI Agent Settings."
            elif "rate limit" in error_str or "quota" in error_str:
                return f"The AI service is currently rate limited{model_info}. Please wait a moment before trying again, or consider using a free model from the dropdown."
            elif "authentication" in error_str or "unauthorized" in error_str:
                return f"There's an issue with the API key{model_info}. Please check that your OpenRouter API key is correctly configured in the AI Agent Settings."
            elif "timeout" in error_str:
                return f"The request timed out{model_info}. Please try again with a simpler request."
            else:
                return f"I encountered an error while processing your request{model_info}: {str(e)}. " \
                       f"If this persists, try switching to Claude 3.5 Haiku which is known to work well with function calling."
    
    def run_interactive(self):
        """
        Run an interactive chat session.
        
        Returns when the user types 'exit' or 'quit'.
        """
        print("\nEntering chat interface with LangChain network agent. Type 'exit' to return to CLI.")
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


# Backward compatibility alias
ChatInterface = LangChainChatInterface
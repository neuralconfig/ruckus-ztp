#!/usr/bin/env python3
"""SSH Proxy main entry point."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from ssh_proxy.core.config import ProxyConfig
from ssh_proxy.core.proxy import main as proxy_main


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="SSH Proxy for RUCKUS ZTP - Remote SSH access through WebSocket"
    )
    
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="/etc/ruckus-ztp-proxy/config.ini",
        help="Configuration file path"
    )
    
    parser.add_argument(
        "--server",
        "-s",
        type=str,
        help="WebSocket server URL (overrides config file)"
    )
    
    parser.add_argument(
        "--token",
        "-t",
        type=str,
        help="Authentication token (overrides config file)"
    )
    
    parser.add_argument(
        "--id",
        type=str,
        help="Proxy ID (overrides config file)"
    )
    
    parser.add_argument(
        "--reconnect-interval",
        type=int,
        default=30,
        help="Reconnection interval in seconds"
    )
    
    parser.add_argument(
        "--command-timeout",
        type=int,
        default=60,
        help="SSH command timeout in seconds"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    parser.add_argument(
        "--log-file",
        type=str,
        help="Log file path"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Load configuration
    if args.server and args.token:
        # Create config from command line args
        config = ProxyConfig.from_args(
            server_url=args.server,
            auth_token=args.token,
            proxy_id=args.id,
            reconnect_interval=args.reconnect_interval,
            command_timeout=args.command_timeout,
            log_level="DEBUG" if args.debug else args.log_level,
            log_file=args.log_file
        )
    elif os.path.exists(args.config):
        # Load from config file
        config = ProxyConfig.from_file(args.config)
        
        # Override with command line args
        if args.server:
            config.server_url = args.server
        if args.token:
            config.auth_token = args.token
        if args.id:
            config.proxy_id = args.id
        if args.debug:
            config.log_level = "DEBUG"
        if args.log_file:
            config.log_file = args.log_file
    else:
        print(f"Error: Configuration file not found: {args.config}")
        print("Please provide --server and --token options or create a config file")
        sys.exit(1)
    
    # Run proxy
    try:
        asyncio.run(proxy_main(config))
    except KeyboardInterrupt:
        print("\nShutdown requested")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
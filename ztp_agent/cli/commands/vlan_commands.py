"""
VLAN management commands for CLI.
"""
import os
import csv
import logging
import argparse
from cmd2 import with_category, with_argparser

# Define command categories
CMD_CATEGORY_VLAN = "VLAN Management Commands"

# VLAN types for categorization
VLAN_TYPE_MANAGEMENT = "management"
VLAN_TYPE_WIRELESS = "wireless"
VLAN_TYPE_OTHER = "other"
VLAN_TYPE_DATA = "data"  # Adding data type for backwards compatibility


class VlanCommandsMixin:
    """VLAN management commands for CLI"""
    
    #
    # VLAN Management Commands
    #
    vlan_parser = argparse.ArgumentParser(description='VLAN management')
    vlan_subparsers = vlan_parser.add_subparsers(dest='vlan_command')
    
    # VLAN load subcommand
    vlan_load_parser = vlan_subparsers.add_parser('load', help='Load VLANs from CSV file')
    vlan_load_parser.add_argument('file_path', help='Path to CSV file')
    
    # VLAN add subcommand
    vlan_add_parser = vlan_subparsers.add_parser('add', help='Add a single VLAN')
    vlan_add_parser.add_argument('id', type=int, help='VLAN ID (1-4094)')
    vlan_add_parser.add_argument('name', help='VLAN name')
    vlan_add_parser.add_argument('type', choices=[VLAN_TYPE_MANAGEMENT, VLAN_TYPE_WIRELESS, VLAN_TYPE_OTHER], 
                               help='VLAN type: management, wireless, or other')
    vlan_add_parser.add_argument('--description', help='VLAN description', default='')
    
    # VLAN management subcommand
    vlan_mgmt_parser = vlan_subparsers.add_parser('set-management', help='Set management VLAN')
    vlan_mgmt_parser.add_argument('id', type=int, help='VLAN ID of management VLAN')
    
    @with_category(CMD_CATEGORY_VLAN)
    @with_argparser(vlan_parser)
    def do_vlan(self, args):
        """VLAN management commands"""
        if not args.vlan_command:
            self.do_help('vlan')
            return
            
        if args.vlan_command == 'load':
            self._load_vlans_from_csv(args.file_path)
        elif args.vlan_command == 'add':
            self._add_vlan(args.id, args.name, args.type, args.description)
        elif args.vlan_command == 'set-management':
            self._set_management_vlan(args.id)
    
    def _load_vlans_from_csv(self, file_path: str):
        """
        Load VLANs from a CSV file.
        
        Expected CSV format:
        id,name,type,description
        10,Management,management,Management network
        20,Data,data,Data network
        30,Voice,voice,Voice over IP
        40,Wireless,wireless,Wireless clients
        50,Guest,guest,Guest network
        """
        try:
            # Convert relative path to absolute
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)
                
            if not os.path.exists(file_path):
                self.perror(f"File not found: {file_path}")
                return
                
            # Clear existing VLANs
            old_vlan_count = len(self.vlans)
            self.vlans = {}
            
            # Read the CSV file
            with open(file_path, 'r') as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    try:
                        vlan_id = int(row['id'])
                        if vlan_id < 1 or vlan_id > 4094:
                            self.perror(f"Invalid VLAN ID: {vlan_id} (must be 1-4094), skipping")
                            continue
                            
                        vlan_type = row['type'].lower()
                        # Map old types to new simplified types
                        if vlan_type == "management":
                            vlan_type = VLAN_TYPE_MANAGEMENT
                        elif vlan_type == "wireless":
                            vlan_type = VLAN_TYPE_WIRELESS
                        elif vlan_type not in [VLAN_TYPE_MANAGEMENT, VLAN_TYPE_WIRELESS]:
                            # All other types map to "other"
                            vlan_type = VLAN_TYPE_OTHER
                            
                        # Create VLAN object
                        vlan = self.VLAN(
                            id=vlan_id,
                            name=row['name'],
                            type=vlan_type,
                            description=row.get('description', '')
                        )
                        
                        # Add to dictionary
                        self.vlans[vlan_id] = vlan
                        
                        # Set as management VLAN if it's the first management VLAN found
                        if vlan_type == VLAN_TYPE_MANAGEMENT and not any(
                            v.type == VLAN_TYPE_MANAGEMENT for v in self.vlans.values() 
                            if v.id != vlan_id
                        ):
                            self.default_management_vlan_id = vlan_id
                    
                    except KeyError as e:
                        self.perror(f"Missing required column in CSV: {e}")
                        return
                        
            # Report success
            self.poutput(f"Loaded {len(self.vlans)} VLANs from {file_path}")
            self.poutput(f"Previous VLAN count: {old_vlan_count}")
            self.poutput(f"Management VLAN ID: {self.default_management_vlan_id}")
            
        except Exception as e:
            self.perror(f"Error loading VLANs from CSV: {e}")
    
    def _add_vlan(self, vlan_id: int, name: str, vlan_type: str, description: str = ""):
        """Add a single VLAN"""
        try:
            if vlan_id < 1 or vlan_id > 4094:
                self.perror(f"Invalid VLAN ID: {vlan_id} (must be 1-4094)")
                return
                
            # Create VLAN object
            vlan = self.VLAN(
                id=vlan_id,
                name=name,
                type=vlan_type,
                description=description
            )
            
            # Add to dictionary
            self.vlans[vlan_id] = vlan
            
            # Set as management VLAN if it's of type management and we don't have one yet
            if vlan_type == VLAN_TYPE_MANAGEMENT and not any(
                v.type == VLAN_TYPE_MANAGEMENT for v in self.vlans.values() 
                if v.id != vlan_id
            ):
                self.default_management_vlan_id = vlan_id
                
            self.poutput(f"Added VLAN {vlan_id} ({name})")
            
        except Exception as e:
            self.perror(f"Error adding VLAN: {e}")
    
    def _set_management_vlan(self, vlan_id: int):
        """Set the management VLAN ID"""
        if vlan_id not in self.vlans:
            self.perror(f"VLAN {vlan_id} not found")
            return
            
        vlan = self.vlans[vlan_id]
        if vlan.type != VLAN_TYPE_MANAGEMENT:
            self.poutput(f"Warning: VLAN {vlan_id} is of type '{vlan.type}', not 'management'")
            self.poutput("Setting it as management VLAN anyway, but you may want to update its type")
            
        self.default_management_vlan_id = vlan_id
        self.poutput(f"Management VLAN set to {vlan_id} ({vlan.name})")
    
    def _show_vlans(self):
        """Show configured VLANs"""
        if not self.vlans:
            self.poutput("No VLANs configured")
            self.poutput("Use 'vlan load <file_path>' to load VLANs from a CSV file")
            self.poutput("  or 'vlan add <id> <n> <type>' to add individual VLANs")
            return
            
        # Create a formatted table
        self.poutput("\nConfigured VLANs:")
        self.poutput("--------------------------------------------------")
        self.poutput(f"{'ID':<5} {'Name':<20} {'Type':<10} {'Description'}")
        self.poutput("--------------------------------------------------")
        
        # First show management VLANs
        management_vlans = [v for v in self.vlans.values() if v.type == VLAN_TYPE_MANAGEMENT]
        for vlan in sorted(management_vlans, key=lambda v: v.id):
            if vlan.id == self.default_management_vlan_id:
                self.poutput(f"{vlan} (default)")
            else:
                self.poutput(f"{vlan}")
                
        # Then show wireless VLANs
        wireless_vlans = [v for v in self.vlans.values() if v.type == VLAN_TYPE_WIRELESS]
        for vlan in sorted(wireless_vlans, key=lambda v: v.id):
            self.poutput(f"{vlan}")
            
        # Then show other VLANs
        other_vlans = [v for v in self.vlans.values() 
                     if v.type == VLAN_TYPE_OTHER]
        for vlan in sorted(other_vlans, key=lambda v: v.id):
            self.poutput(f"{vlan}")
            
        self.poutput("--------------------------------------------------")
        self.poutput(f"Total VLANs: {len(self.vlans)}")
        self.poutput(f"Management VLANs: {len(management_vlans)}")
        self.poutput(f"Wireless VLANs: {len(wireless_vlans)}")
        self.poutput(f"Other VLANs: {len(other_vlans)}")
        self.poutput("--------------------------------------------------\n")
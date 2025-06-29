#!/usr/bin/env python3
"""
LinAIx Natural Language Terminal: AI-powered shell
A secure, AI-powered tool for generating and executing Linux commands.
Type what you want to do in plain English. No shell commands allowed!
All actions are interpreted and executed by AI with security validation.
"""
import sys
import os
import re
import json
import time
import subprocess
import shlex
import logging
from pathlib import Path
import argparse
import google.generativeai as genai
import shutil
from typing import Optional, Tuple, Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
CONFIG_DIR = Path.home() / ".linaix"
CONFIG_FILE = CONFIG_DIR / "config.json"

# ANSI color codes
ANSI_GREEN = "\033[1;32m"
ANSI_RED = "\033[1;31m"
ANSI_YELLOW = "\033[1;33m"
ANSI_BLUE = "\033[1;34m"
ANSI_CYAN = "\033[1;36m"
ANSI_MAGENTA = "\033[1;35m"
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"

# Security constants
MAX_INPUT_LENGTH = 1000
MAX_COMMAND_LENGTH = 500
COMMAND_TIMEOUT = 30

# Security: Whitelist of safe commands
SAFE_COMMANDS = {
    'cd', 'ls', 'pwd', 'mkdir', 'touch', 'cat', 'echo', 'head', 'tail',
    'grep', 'find', 'wc', 'sort', 'uniq', 'cut', 'tr', 'sed', 'awk',
    'df', 'du', 'free', 'ps', 'top', 'htop', 'who', 'whoami', 'date',
    'cal', 'uptime', 'uname', 'hostname', 'which', 'whereis', 'locate',
    'file', 'stat', 'chmod', 'chown', 'cp', 'mv', 'ln', 'rm', 'rmdir',
    'tar', 'gzip', 'gunzip', 'zip', 'unzip', 'wget', 'curl', 'git',
    'apt', 'apt-get', 'dpkg', 'snap', 'pip', 'python', 'python3',
    'node', 'npm', 'npx', 'docker', 'docker-compose'
}

# Security: Dangerous commands that require extra confirmation
DANGEROUS_COMMANDS = {
    'rm', 'dd', 'chmod', 'chown', 'mkfs', 'fdisk', 'parted', 'mount',
    'umount', 'shutdown', 'reboot', 'halt', 'poweroff', 'kill', 'killall',
    'pkill', 'systemctl', 'service', 'iptables', 'ufw', 'firewall-cmd'
}

# Security: Commands that should never be executed
BLOCKED_COMMANDS = {
    'sudo', 'su', 'doas', 'pkexec', 'gksudo', 'kdesudo', 'xdg-sudo'
}

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "gemini-1.5-flash",
    "auto_run_safe": False,
    "aliases": {}
}

class SecurityError(Exception):
    """Custom exception for security violations."""
    pass

class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

def validate_input(user_input: str) -> str:
    """
    Validate and sanitize user input.
    
    Args:
        user_input: Raw user input string
        
    Returns:
        Sanitized input string
        
    Raises:
        ValidationError: If input is invalid or too long
    """
    if not user_input or not isinstance(user_input, str):
        raise ValidationError("Input must be a non-empty string")
    
    # Check length
    if len(user_input) > MAX_INPUT_LENGTH:
        raise ValidationError(f"Input too long (max {MAX_INPUT_LENGTH} characters)")
    
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"|&`$]', '', user_input.strip())
    
    # Check for command injection attempts
    dangerous_patterns = [
        r'[;&|`$]',  # Command separators
        r'\(.*\)',   # Subshells
        r'\$\{.*\}', # Variable expansion
        r'<.*>',     # Redirections
        r'\\',       # Escapes
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, sanitized):
            raise ValidationError("Input contains potentially dangerous characters")
    
    return sanitized

def validate_command(command: str) -> str:
    """
    Validate and sanitize generated command.
    
    Args:
        command: Generated command string
        
    Returns:
        Sanitized command string
        
    Raises:
        SecurityError: If command is blocked or dangerous
    """
    if not command or not isinstance(command, str):
        raise SecurityError("Invalid command")
    
    if len(command) > MAX_COMMAND_LENGTH:
        raise SecurityError(f"Command too long (max {MAX_COMMAND_LENGTH} characters)")
    
    # Split command into parts for analysis
    try:
        parts = shlex.split(command)
        if not parts:
            raise SecurityError("Empty command")
        
        base_command = parts[0].lower()
        
        # Check for blocked commands
        if base_command in BLOCKED_COMMANDS:
            raise SecurityError(f"Command '{base_command}' is blocked for security reasons")
        
        # Check for dangerous commands
        if base_command in DANGEROUS_COMMANDS:
            logger.warning(f"Dangerous command detected: {base_command}")
        
        # Check for safe commands (optional whitelist)
        if base_command not in SAFE_COMMANDS:
            logger.warning(f"Unknown command: {base_command}")
        
        return command.strip()
        
    except ValueError as e:
        raise SecurityError(f"Invalid command syntax: {e}")

def secure_subprocess_run(command: str, **kwargs) -> subprocess.CompletedProcess:
    """
    Securely run a subprocess command with proper validation.
    
    Args:
        command: Command to execute
        **kwargs: Additional arguments for subprocess.run
        
    Returns:
        CompletedProcess object
        
    Raises:
        SecurityError: If command is unsafe
    """
    # Validate command
    validated_command = validate_command(command)
    
    # Use list format instead of shell=True for better security
    try:
        cmd_parts = shlex.split(validated_command)
        return subprocess.run(cmd_parts, **kwargs)
    except Exception as e:
        logger.error(f"Subprocess execution failed: {e}")
        raise SecurityError(f"Command execution failed: {e}")

def load_config() -> Dict[str, Any]:
    """
    Load configuration with proper error handling and security.
    
    Returns:
        Configuration dictionary
        
    Raises:
        SystemExit: If configuration cannot be loaded
    """
    try:
        if not CONFIG_DIR.exists():
            CONFIG_DIR.mkdir(mode=0o700)  # Secure permissions
        
        if not CONFIG_FILE.exists() or CONFIG_FILE.stat().st_size == 0:
            with CONFIG_FILE.open("w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            os.chmod(CONFIG_FILE, 0o600)  # Secure permissions
        
        with CONFIG_FILE.open("r") as f:
            config = json.load(f)
        
        # Validate config structure
        if not isinstance(config, dict):
            raise ValueError("Invalid config format")
        
        # Ensure all required keys exist
        for key, default_value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = default_value
        
        # Get API key from environment if not in config
        if not config["api_key"] and "GOOGLE_API_KEY" in os.environ:
            config["api_key"] = os.environ["GOOGLE_API_KEY"]
        
        if not config["api_key"]:
            print(f"{ANSI_RED}Error: No Google API key found. Set it in {CONFIG_FILE} or export GOOGLE_API_KEY.{ANSI_RESET}")
            sys.exit(1)
        
        return config
        
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.error(f"Failed to load config: {e}")
        print(f"{ANSI_RED}Error: Failed to load configuration: {e}{ANSI_RESET}")
        sys.exit(1)

# Load configuration and initialize Gemini
try:
    config = load_config()
    genai.configure(api_key=config["api_key"])
except Exception as e:
    logger.error(f"Failed to initialize: {e}")
    sys.exit(1)

def generate_command(user_input: str, error_context: Optional[str] = None, verbose: bool = False) -> Tuple[Optional[str], str]:
    """
    Generate a Linux command using Gemini API with proper validation.
    
    Args:
        user_input: Natural language description of the task
        error_context: Previous error message for correction
        verbose: Whether to include explanations
        
    Returns:
        Tuple of (command, explanation)
    """
    try:
        # Validate input
        validated_input = validate_input(user_input)
        
        model = genai.GenerativeModel(config["model"])
        current_dir = os.getcwd()
        
        # Create a secure prompt
        prompt = f"Generate a single, safe, correct Linux command for a Debian-based system to: {validated_input}. Current directory: {current_dir}. Return only the command."
        
        if error_context:
            prompt += f" Previous command failed with error: '{error_context}'. Suggest a corrected command."
        
        if verbose:
            prompt += " Additionally, return a brief explanation in the format: [EXPLANATION: ...]"
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Extract command and explanation
        command = re.sub(r'```bash\n|```|\n\[EXPLANATION:.*', '', text).strip()
        explanation = re.search(r'\[EXPLANATION: (.*?)\]', text)
        explanation = explanation.group(1) if explanation else ""
        
        # Validate generated command
        if not command:
            return None, ""
        
        validated_command = validate_command(command)
        return validated_command, explanation
        
    except ValidationError as e:
        logger.error(f"Input validation failed: {e}")
        print(f"{ANSI_RED}Error: Invalid input - {e}{ANSI_RESET}")
        return None, ""
    except SecurityError as e:
        logger.error(f"Security validation failed: {e}")
        print(f"{ANSI_RED}Error: Security violation - {e}{ANSI_RESET}")
        return None, ""
    except Exception as e:
        logger.error(f"Command generation failed: {e}")
        print(f"{ANSI_RED}Error: Could not generate command: {str(e)}{ANSI_RESET}")
        return None, ""

def run_command(command: str) -> Tuple[bool, str]:
    """
    Run command with proper security validation.
    
    Args:
        command: Command to execute
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Handle cd command specially
        if command.strip().startswith("cd "):
            try:
                new_dir = command.strip().split(" ", 1)[1]
                os.chdir(os.path.expanduser(new_dir))
                print(f"{ANSI_GREEN}Changed directory to: {os.getcwd()}{ANSI_RESET}")
                return True, ""
            except Exception as e:
                logger.error(f"Failed to change directory: {e}")
                return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

        # Use secure subprocess execution
        result = secure_subprocess_run(command, text=True, capture_output=True, timeout=COMMAND_TIMEOUT)
        
        if result.stdout:
            print(f"{ANSI_CYAN}Output:{ANSI_RESET}\n{result.stdout.strip()}")
        if result.stderr:
            print(f"{ANSI_RED}Error:{ANSI_RESET}\n{result.stderr.strip()}")
        
        return result.returncode == 0, result.stderr.strip()
        
    except subprocess.TimeoutExpired:
        return False, f"{ANSI_RED}Error: Command timed out after {COMMAND_TIMEOUT} seconds{ANSI_RESET}"
    except SecurityError as e:
        return False, f"{ANSI_RED}Error: {e}{ANSI_RESET}"
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

def print_centered(text: str, color: str = "") -> None:
    """
    Print text centered in terminal.
    
    Args:
        text: Text to print
        color: ANSI color code
    """
    try:
        width = shutil.get_terminal_size((80, 20)).columns
        for line in text.splitlines():
            if line.strip() == "":
                print()
            else:
                print(color + line.center(width) + ANSI_RESET)
    except Exception:
        # Fallback if terminal size cannot be determined
        for line in text.splitlines():
            if line.strip() == "":
                print()
            else:
                print(color + line + ANSI_RESET)

def print_linaix_banner() -> None:
    """
    Print the LinAIx banner.
    """
    banner = f"""
██╗     ██╗███╗   ██╗ █████╗ ██╗██╗  ██╗
██║     ██║████╗  ██║██╔══██╗██║╚██╗██╔╝
██║     ██║██╔██╗ ██║███████║██║ ╚███╔╝ 
██║     ██║██║╚██╗██║██╔══██║██║ ██╔██╗ 
███████╗██║██║ ╚████║██║  ██║██║██╔╝ ██╗
╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
"""
    print_centered(banner, ANSI_GREEN + ANSI_BOLD)

def print_intro() -> None:
    """
    Print introduction and usage information.
    """
    try:
        width = shutil.get_terminal_size((80, 20)).columns
        border = "+" + ("-" * (width - 2)) + "+"
    except Exception:
        border = "+" + ("-" * 78) + "+"
    
    print(ANSI_MAGENTA + border + ANSI_RESET)
    print_centered("Welcome to LinAIx Natural Language Terminal!", ANSI_MAGENTA + ANSI_BOLD)
    print_centered("AI-powered Linux shell: Just describe what you want to do!", ANSI_CYAN)
    print_centered("Type 'exit' to quit.", ANSI_YELLOW)
    print_centered("", ANSI_RESET)
    print_centered("Usage Examples:", ANSI_BOLD + ANSI_CYAN)
    print_centered("- create a new folder called test", ANSI_CYAN)
    print_centered("- list all python files", ANSI_CYAN)
    print_centered("- show disk usage", ANSI_CYAN)
    print_centered("- move all .txt files to backup/", ANSI_CYAN)
    print_centered("- install the latest version of git", ANSI_CYAN)
    print_centered("", ANSI_RESET)
    print_centered("Tips:", ANSI_BOLD + ANSI_GREEN)
    print_centered("• Only natural language tasks are accepted.", ANSI_GREEN)
    print_centered("• No raw shell commands.", ANSI_GREEN)
    print_centered("• Destructive actions (like rm) will ask for confirmation.", ANSI_GREEN)
    print_centered("• Have fun!", ANSI_GREEN)
    print(ANSI_MAGENTA + border + ANSI_RESET)

def nl_terminal(verbose: bool = False) -> None:
    """
    Run the natural language terminal interface.
    
    Args:
        verbose: Whether to show verbose output
    """
    print_linaix_banner()
    print_intro()
    
    while True:
        try:
            # Get user and host information safely
            user = os.getenv('USER') or os.getenv('USERNAME') or 'user'
            
            try:
                host = os.uname().nodename if hasattr(os, 'uname') else 'host'
            except Exception:
                host = 'host'
            
            cwd = os.getcwd()
            prompt = f"{ANSI_GREEN}{user}@{host}{ANSI_RESET}:{ANSI_BLUE}{cwd}{ANSI_RESET} $ "
            
            user_input = input(prompt).strip()
            if not user_input:
                continue
                
            if user_input.lower() in ['exit', 'quit']:
                print(f"{ANSI_GREEN}Goodbye!{ANSI_RESET}")
                break
            
            # Validate input before processing
            try:
                validated_input = validate_input(user_input)
            except ValidationError as e:
                print(f"{ANSI_RED}Invalid input: {e}{ANSI_RESET}")
                continue
            
            command, explanation = generate_command(validated_input, verbose=verbose)
            
            if not command:
                print(f"{ANSI_RED}Could not generate a command for your request.{ANSI_RESET}")
                continue
            
            print(f"{ANSI_BLUE}Generated Command:{ANSI_RESET} {ANSI_GREEN}{command}{ANSI_RESET}")
            if verbose and explanation:
                print(f"{ANSI_BLUE}Explanation:{ANSI_RESET} {ANSI_CYAN}{explanation}{ANSI_RESET}")
            
            success, error = run_command(command)
            if success:
                print(f"{ANSI_GREEN}✓ Success{ANSI_RESET}")
            else:
                print(f"{ANSI_RED}✗ Error: {error}{ANSI_RESET}")
                
        except (EOFError, KeyboardInterrupt):
            print(f"\n{ANSI_GREEN}Goodbye!{ANSI_RESET}")
            break
        except Exception as e:
            logger.error(f"Unexpected error in terminal: {e}")
            print(f"{ANSI_RED}Unexpected error: {e}{ANSI_RESET}")

def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(description="LinAIx Natural Language Terminal")
    parser.add_argument("--verbose", action="store_true", help="Show explanations for generated commands")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    nl_terminal(verbose=args.verbose)
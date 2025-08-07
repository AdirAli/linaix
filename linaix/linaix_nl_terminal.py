#!/usr/bin/env python3

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".linaix"
CONFIG_FILE = CONFIG_DIR / "config.json"

ANSI_GREEN = "\033[1;32m"
ANSI_RED = "\033[1;31m"
ANSI_YELLOW = "\033[1;33m"
ANSI_BLUE = "\033[1;34m"
ANSI_CYAN = "\033[1;36m"
ANSI_MAGENTA = "\033[1;35m"
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"

MAX_INPUT_LENGTH = 1000
MAX_COMMAND_LENGTH = 500
COMMAND_TIMEOUT = 30

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

DANGEROUS_COMMANDS = {
    'rm', 'dd', 'chmod', 'chown', 'mkfs', 'fdisk', 'parted', 'mount',
    'umount', 'shutdown', 'reboot', 'halt', 'poweroff', 'kill', 'killall',
    'pkill', 'systemctl', 'service', 'iptables', 'ufw', 'firewall-cmd'
}

BLOCKED_COMMANDS = {
    'sudo', 'su', 'doas', 'pkexec', 'gksudo', 'kdesudo', 'xdg-sudo'
}

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "gemini-1.5-flash",
    "auto_run_safe": False,
    "aliases": {}
}

config = None

class SecurityError(Exception):
    pass

class ValidationError(Exception):
    pass

def detect_linux_distribution() -> str:
    
    try:
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                os_release = f.read()
            
            distro_name = None
            distro_version = None
            
            for line in os_release.split('\n'):
                if line.startswith('PRETTY_NAME='):
                    distro_name = line.split('=', 1)[1].strip().strip('"')
                    break
                elif line.startswith('NAME='):
                    distro_name = line.split('=', 1)[1].strip().strip('"')
                elif line.startswith('VERSION='):
                    distro_version = line.split('=', 1)[1].strip().strip('"')
            
            if distro_name:
                if distro_version and distro_version not in distro_name:
                    return f"{distro_name} {distro_version}"
                return distro_name
        
        if os.path.exists('/etc/issue'):
            with open('/etc/issue', 'r') as f:
                issue_content = f.read().strip()
                if issue_content:
                    return issue_content.split('\n')[0].strip()
        
        try:
            result = subprocess.run(['uname', '-a'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        return "Linux (unknown distribution)"
        
    except Exception as e:
        logger.warning(f"Failed to detect Linux distribution: {e}")
        return "Linux (unknown distribution)"

def validate_input(user_input: str) -> str:
    
    if not user_input or not isinstance(user_input, str):
        raise ValidationError("Input must be a non-empty string")
    
    if len(user_input) > MAX_INPUT_LENGTH:
        raise ValidationError(f"Input too long (max {MAX_INPUT_LENGTH} characters)")
    
    sanitized = re.sub(r'[<>"|&`$]', '', user_input.strip())
    
    dangerous_patterns = [
        r'[;&|`$]',  
        r'\(.*\)',   
        r'\$\{.*\}', 
        r'<.*>',     
        r'\\',       
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, sanitized):
            raise ValidationError("Input contains potentially dangerous characters")
    
    return sanitized

def validate_command(command: str) -> str:
    
    if not command or not isinstance(command, str):
        raise SecurityError("Invalid command")
    
    if len(command) > MAX_COMMAND_LENGTH:
        raise SecurityError(f"Command too long (max {MAX_COMMAND_LENGTH} characters)")
    
    try:
        parts = shlex.split(command)
        if not parts:
            raise SecurityError("Empty command")
        
        base_command = parts[0].lower()
            
        if base_command in BLOCKED_COMMANDS:
            raise SecurityError(f"Command '{base_command}' is blocked for security reasons")
        
        if base_command in DANGEROUS_COMMANDS:
            logger.warning(f"Dangerous command detected: {base_command}")
        
        if base_command not in SAFE_COMMANDS:
            logger.warning(f"Unknown command: {base_command}")
        
        return command.strip()
        
    except ValueError as e:
        raise SecurityError(f"Invalid command syntax: {e}")

def secure_subprocess_run(command: str, **kwargs) -> subprocess.CompletedProcess:
   
    
    validated_command = validate_command(command)
    
    
    try:
        cmd_parts = shlex.split(validated_command)
        return subprocess.run(cmd_parts, **kwargs)
    except Exception as e:
        logger.error(f"Subprocess execution failed: {e}")
        raise SecurityError(f"Command execution failed: {e}")

def load_config() -> Dict[str, Any]:
   
    try:
        if not CONFIG_DIR.exists():
            CONFIG_DIR.mkdir(mode=0o700)  
        
        if not CONFIG_FILE.exists() or CONFIG_FILE.stat().st_size == 0:
            with CONFIG_FILE.open("w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            os.chmod(CONFIG_FILE, 0o600)  
        
        with CONFIG_FILE.open("r") as f:
            config = json.load(f)
        
        
        if not isinstance(config, dict):
            raise ValueError("Invalid config format")
        
        
        for key, default_value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = default_value
        
        
        if not config["api_key"] and "GOOGLE_API_KEY" in os.environ:
            config["api_key"] = os.environ["GOOGLE_API_KEY"]
        
        return config
        
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.error(f"Failed to load config: {e}")
        print(f"{ANSI_RED}Error: Failed to load configuration: {e}{ANSI_RESET}")
        sys.exit(1)

def validate_api_key() -> None:
    
    global config
    if config is None:
        config = load_config()
    
    if not config["api_key"]:
        print(f"{ANSI_RED}Error: No Google API key found.{ANSI_RESET}")
        print(f"{ANSI_YELLOW}To set up your API key:{ANSI_RESET}")
        print(f"  1. Run: {ANSI_GREEN}linaix --setup{ANSI_RESET} for interactive setup")
        print(f"  2. Or run: {ANSI_GREEN}linaix --set-api-key{ANSI_RESET} to set it directly")
        print(f"  3. Or obtain a Google API key from https://aistudio.google.com/app/apikey")
        print(f"  4. Then set it in {CONFIG_FILE} or export GOOGLE_API_KEY='your-api-key'")
        print(f"\n{ANSI_BLUE}For more help, run: {ANSI_GREEN}linaix --help{ANSI_RESET}")
        sys.exit(1)



def generate_command(user_input: str, error_context: Optional[str] = None, verbose: bool = False) -> Tuple[Optional[str], str]:
    global config
    
    try:
        validate_api_key()
        
        if not genai.configure():
            genai.configure(api_key=config["api_key"])
        
        validated_input = validate_input(user_input)
        
        model = genai.GenerativeModel(config["model"])
        current_dir = os.getcwd()
        distro_info = detect_linux_distribution()
        
        
        prompt = f"Generate a single, safe, correct Linux command for {distro_info} to: {validated_input}. Current directory: {current_dir}. Return only the command."
        
        if error_context:
            prompt += f" Previous command failed with error: '{error_context}'. Suggest a corrected command."
        
        if verbose:
            prompt += " Additionally, return a brief explanation in the format: [EXPLANATION: ...]"
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        
        command = re.sub(r'```bash\n|```|\n\[EXPLANATION:.*', '', text).strip()
        explanation = re.search(r'\[EXPLANATION: (.*?)\]', text)
        explanation = explanation.group(1) if explanation else ""
        
        
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
    
    try:
        
        if command.strip().startswith("cd "):
            try:
                new_dir = command.strip().split(" ", 1)[1]
                os.chdir(os.path.expanduser(new_dir))
                print(f"{ANSI_GREEN}Changed directory to: {os.getcwd()}{ANSI_RESET}")
                return True, ""
            except Exception as e:
                logger.error(f"Failed to change directory: {e}")
                return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

        
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
   
    try:
        width = shutil.get_terminal_size((80, 20)).columns
        for line in text.splitlines():
            if line.strip() == "":
                print()
            else:
                print(color + line.center(width) + ANSI_RESET)
    except Exception:
        
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
    print_linaix_banner()
    print_intro()
    
    while True:
        try:
            
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
    
    parser = argparse.ArgumentParser(description="LinAIx Natural Language Terminal")
    parser.add_argument("--verbose", action="store_true", help="Show explanations for generated commands")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    nl_terminal(verbose=args.verbose)
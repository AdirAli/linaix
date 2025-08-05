#!/usr/bin/env python3
"""
LinAIx: Linux Command Assistant powered by Gemini API
"""
import sys
import os
import google.generativeai as genai
import re
import json
import time
import subprocess
import shlex
import logging
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
import argparse
import shutil
from typing import Optional, Tuple, Dict, Any, List
import platform

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".linaix"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

ANSI_GREEN = "\033[1;32m"
ANSI_RED = "\033[1;31m"
ANSI_YELLOW = "\033[1;33m"
ANSI_BLUE = "\033[1;34m"
ANSI_CYAN = "\033[1;36m"
ANSI_MAGENTA = "\033[1;35m"
ANSI_RESET = "\033[0m"
ANSI_SEPARATOR = "\033[1;34m" + "-" * 40 + "\033[0m"
ANSI_BOLD = "\033[1m"

PTK_GREEN = "ansigreen"
PTK_RED = "ansired"
PTK_YELLOW = "ansiyellow"
PTK_BLUE = "ansiblue"
PTK_CYAN = "ansicyan"
PTK_MAGENTA = "ansimagenta"

STYLE_DICT = {
    'prompt': f'{PTK_GREEN} bold',
    'output': '#ffffff',
    'command': f'{PTK_GREEN}',
    'explanation': f'{PTK_CYAN}',
    'error': f'{PTK_RED}',
    'header': f'{PTK_MAGENTA} bold',
    'info': f'{PTK_CYAN}',
    'separator': f'{PTK_BLUE}',
}
STYLE = Style.from_dict(STYLE_DICT)

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

HISTORY_LIMIT = 100
MAX_INPUT_LENGTH = 1000
MAX_COMMAND_LENGTH = 500

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "gemini-1.5-flash",
    "auto_run_safe": False,
    "aliases": {}
}

class SecurityError(Exception):
    pass

class ValidationError(Exception):
    pass

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
        
        if not config["api_key"]:
            print(f"{ANSI_RED}Error: No Google API key found. Set it in {CONFIG_FILE} or export GOOGLE_API_KEY.{ANSI_RESET}")
            sys.exit(1)
        
        return config
        
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.error(f"Failed to load config: {e}")
        print(f"{ANSI_RED}Error: Failed to load configuration: {e}{ANSI_RESET}")
        sys.exit(1)

def save_config(config: Dict[str, Any]) -> None:
    """
    Save configuration with proper error handling.
    
    Args:
        config: Configuration dictionary to save
    """
    try:
        if not CONFIG_DIR.exists():
            CONFIG_DIR.mkdir(mode=0o700)
        
        with CONFIG_FILE.open("w") as f:
            json.dump(config, f, indent=2)
        
        os.chmod(CONFIG_FILE, 0o600)  
        
    except (OSError, TypeError) as e:
        logger.error(f"Failed to save config: {e}")
        print(f"{ANSI_RED}Error: Failed to save configuration: {e}{ANSI_RESET}")

def save_history(user_input: str, command: str) -> None:
   
    try:
        user_input = validate_input(user_input)
        command = validate_command(command)
        
        history = []
        if HISTORY_FILE.exists():
            with HISTORY_FILE.open("r") as f:
                history = json.load(f)
        
        if not isinstance(history, list):
            history = []
        
        history.append({"input": user_input, "command": command})
        
        history = history[-HISTORY_LIMIT:]
        
        with HISTORY_FILE.open("w") as f:
            json.dump(history, f, indent=2)
        
        os.chmod(HISTORY_FILE, 0o600)  
        
    except Exception as e:
        logger.error(f"Failed to save history: {e}")

def load_history() -> List[Dict[str, str]]:
   
    try:
        if HISTORY_FILE.exists():
            with HISTORY_FILE.open("r") as f:
                history = json.load(f)
            
            if not isinstance(history, list):
                return []
            
            return history
        return []
        
    except Exception as e:
        logger.error(f"Failed to load history: {e}")
        return []

def get_history_command(index: str) -> Tuple[Optional[str], Optional[str]]:
    
    try:
        history = load_history()
        idx = int(index)
        
        if 0 <= idx < len(history):
            entry = history[idx]
            return entry.get("command"), entry.get("input")
        
        return None, None
        
    except (ValueError, IndexError, KeyError):
        return None, None

def get_autocomplete_suggestions() -> List[str]:
    """
    Get autocomplete suggestions from history.
    
    Returns:
        List of user input strings for autocomplete
    """
    try:
        history = load_history()
        return [entry.get("input", "") for entry in history if entry.get("input")]
    except Exception as e:
        logger.error(f"Failed to get autocomplete suggestions: {e}")
        return []

try:
    config = load_config()
    genai.configure(api_key=config["api_key"])
except Exception as e:
    logger.error(f"Failed to initialize: {e}")
    sys.exit(1)

def generate_command(user_input: str, error_context: Optional[str] = None, verbose: bool = False) -> Tuple[str, str]:
    
    try:
        validated_input = validate_input(user_input)
        
        model = genai.GenerativeModel(config["model"])
        current_dir = os.getcwd()
        
        prompt = f"Generate a single, safe, correct Linux command for a Debian-based system to: {validated_input}. Current directory: {current_dir}. Return only the command, no explanations."
        
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
            return f"{ANSI_RED}Error: No valid command generated.{ANSI_RESET}", ""
        
        validated_command = validate_command(command)
        return validated_command, explanation
        
    except ValidationError as e:
        logger.error(f"Input validation failed: {e}")
        return f"{ANSI_RED}Error: Invalid input - {e}{ANSI_RESET}", ""
    except SecurityError as e:
        logger.error(f"Security validation failed: {e}")
        return f"{ANSI_RED}Error: Security violation - {e}{ANSI_RESET}", ""
    except Exception as e:
        logger.error(f"Command generation failed: {e}")
        return f"{ANSI_RED}Error: Could not generate command: {str(e)}{ANSI_RESET}", ""

def get_error_explanation(error: str) -> str:
    
    try:
        if not error or not isinstance(error, str):
            return f"{ANSI_RED}Invalid error message.{ANSI_RESET}"
        
        if len(error) > MAX_INPUT_LENGTH:
            error = error[:MAX_INPUT_LENGTH] + "..."
        
        model = genai.GenerativeModel(config["model"])
        response = model.generate_content(f"Explain this Linux command error briefly: '{error}'")
        return response.text.strip()
        
    except Exception as e:
        logger.error(f"Error explanation failed: {e}")
        return f"{ANSI_RED}Unable to explain error.{ANSI_RESET}"

def simulate_typing(command: str) -> None:
    
    print(f"{ANSI_BLUE}Executing command:{ANSI_RESET} ", end="", flush=True)
    for char in command:
        print(char, end="", flush=True)
        time.sleep(0.05)
    print()

def run_command_interactive(command: str, verbose: bool = False) -> Tuple[bool, str]:
    try:
        if command.strip().startswith("cd "):
            try:
                new_dir = command.strip().split(" ", 1)[1]
                os.chdir(os.path.expanduser(new_dir))
                print(f"{ANSI_GREEN}Changed directory to: {os.getcwd()}{ANSI_RESET}")
                return True, ""
            except Exception as e:
                return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

        simulate_typing(command)

        result = secure_subprocess_run(command, text=True, capture_output=True, timeout=30)
        
        if result.stdout:
            print(f"{ANSI_CYAN}Output:{ANSI_RESET}")
            print(result.stdout.strip())
        if result.stderr:
            print(f"{ANSI_RED}Error:{ANSI_RESET}")
            print(result.stderr.strip())
        
        return result.returncode == 0, result.stderr.strip()
        
    except subprocess.TimeoutExpired:
        return False, f"{ANSI_RED}Error: Command timed out after 30 seconds{ANSI_RESET}"
    except SecurityError as e:
        return False, f"{ANSI_RED}Error: {e}{ANSI_RESET}"
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

def run_command_normal(command: str, verbose: bool = False) -> Tuple[bool, str]:
    try:
        if command.strip().startswith("cd "):
            try:
                new_dir = command.strip().split(" ", 1)[1]
                os.chdir(os.path.expanduser(new_dir))
                print(f"{ANSI_GREEN}Changed directory to: {os.getcwd()}{ANSI_RESET}")
                return True, ""
            except Exception as e:
                return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

        cmd_parts = shlex.split(command)
        if cmd_parts and cmd_parts[0].lower() in DANGEROUS_COMMANDS:
            print(f"{ANSI_YELLOW}Warning: This is a potentially dangerous command!{ANSI_RESET}")
            confirm = input(f"{ANSI_YELLOW}Are you sure you want to execute this command? (yes/no): {ANSI_RESET}").strip().lower()
            if confirm not in ['yes', 'y']:
                print(f"{ANSI_YELLOW}Command not executed.{ANSI_RESET}")
                sys.exit(0)
        else:
            confirm = input(f"{ANSI_YELLOW}Do you want to execute this command? (y/n): {ANSI_RESET}").strip().lower()
            if confirm not in ['y', 'yes']:
                print(f"{ANSI_YELLOW}Command not executed.{ANSI_RESET}")
                sys.exit(0)

        simulate_typing(command)
        
        result = secure_subprocess_run(command, text=True, capture_output=True, timeout=30)
        
        if result.stdout:
            print(f"{ANSI_CYAN}Output:{ANSI_RESET}")
            print(result.stdout.strip())
        if result.stderr:
            print(f"{ANSI_RED}Error:{ANSI_RESET}")
            print(result.stderr.strip())
        
        return result.returncode == 0, result.stderr.strip()
        
    except subprocess.TimeoutExpired:
        return False, f"{ANSI_RED}Error: Command timed out after 30 seconds{ANSI_RESET}"
    except SecurityError as e:
        return False, f"{ANSI_RED}Error: {e}{ANSI_RESET}"
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

def show_changes() -> None:
    """
    Show current directory and contents after command execution.
    """
    print(f"{ANSI_BLUE}Current Directory: {os.getcwd()}{ANSI_RESET}")
    try:
        result = secure_subprocess_run("ls -l", text=True, capture_output=True, timeout=10)
        if result.stdout:
            print(f"{ANSI_CYAN}Directory Contents:{ANSI_RESET}")
            print(result.stdout.strip())
        if result.stderr:
            print(f"{ANSI_RED}Error listing directory:{ANSI_RESET}")
            print(result.stderr.strip())
    except Exception as e:
        logger.error(f"Failed to show directory contents: {e}")
        print(f"{ANSI_RED}Error listing directory: {str(e)}{ANSI_RESET}")

def is_destructive_command(command: str) -> bool:
    try:
        cmd_parts = shlex.split(command)
        return cmd_parts and cmd_parts[0].lower() in DANGEROUS_COMMANDS
    except Exception:
        return False

def print_help() -> None:
   
    print(f"{ANSI_MAGENTA}{'-' * 60}{ANSI_RESET}")
    print(f"{ANSI_MAGENTA}LinAIx: Linux Command Assistant powered by Gemini API{ANSI_RESET}")
    print(f"{ANSI_MAGENTA}{'-' * 60}{ANSI_RESET}")
    print(f"{ANSI_BLUE}Usage:{ANSI_RESET} linaix [options] 'task description'")
    print(f"\n{ANSI_BLUE}Options:{ANSI_RESET}")
    print(f"  {ANSI_GREEN}'task'{ANSI_RESET}            Generate a command for the task (e.g., 'create a python file test.py')")
    print(f"  {ANSI_GREEN}--interactive{ANSI_RESET}     Run in interactive natural language mode")
    print(f"  {ANSI_GREEN}--verbose{ANSI_RESET}         Show command explanations (for direct command generation only)")
    print(f"  {ANSI_GREEN}--history{ANSI_RESET}         Display command history")
    print(f"  {ANSI_GREEN}--reuse <index>{ANSI_RESET}   Reuse command from history by index")
    print(f"  {ANSI_GREEN}--add-alias <name> <task>{ANSI_RESET}  Add an alias (e.g., 'listpy' 'list all python files')")
    print(f"  {ANSI_GREEN}--remove-alias <name>{ANSI_RESET}     Remove an alias")
    print(f"  {ANSI_GREEN}--list-aliases{ANSI_RESET}         List all aliases")
    print(f"  {ANSI_GREEN}--help{ANSI_RESET}            Show this detailed help")
    print(f"  {ANSI_GREEN}--set-api-key{ANSI_RESET}     Set the Google API key interactively")
    print(f"  {ANSI_GREEN}--setup{ANSI_RESET}            Interactive setup for API key and model")
    print(f"\n{ANSI_BLUE}Examples:{ANSI_RESET}")
    print(f"  linaix 'list all python files'          # Generates 'ls *.py' and prompts for execution")
    print(f"  linaix --verbose 'create a directory'   # Includes explanation and prompts")
    print(f"  linaix --interactive                   # Runs natural language AI shell in new terminal")
    print(f"  linaix --add-alias listpy 'list all python files'  # Adds alias")
    print(f"  linaix listpy                          # Uses alias and prompts")
    print(f"\n{ANSI_BLUE}Security Features:{ANSI_RESET}")
    print(f"  • Input validation and sanitization")
    print(f"  • Command whitelist and blacklist")
    print(f"  • Secure subprocess execution")
    print(f"  • Timeout protection (30 seconds)")
    print(f"  • Dangerous command confirmation")
    print(f"\n{ANSI_BLUE}Setup:{ANSI_RESET}")
    print(f"  1. Run: {ANSI_GREEN}linaix --setup{ANSI_RESET} for interactive setup")
    print(f"  2. Or obtain a Google API key from https://aistudio.google.com/app/apikey")
    print(f"  3. Set it in {CONFIG_FILE} or export GOOGLE_API_KEY='your-api-key'")
    print(f"{ANSI_MAGENTA}{'-' * 60}{ANSI_RESET}")

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
            
            if not command or command.startswith(f"{ANSI_RED}Error:"):
                print(f"{ANSI_RED}Could not generate a command for your request.{ANSI_RESET}")
                continue
            
            print(f"{ANSI_BLUE}Generated Command:{ANSI_RESET} {ANSI_GREEN}{command}{ANSI_RESET}")
            if verbose and explanation:
                print(f"{ANSI_BLUE}Explanation:{ANSI_RESET} {ANSI_CYAN}{explanation}{ANSI_RESET}")
            
            success, error = run_command_interactive(command, verbose)
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

def main() -> None:
    
    parser = argparse.ArgumentParser(description="Linux Command Assistant", add_help=False)
    parser.add_argument("task", nargs="*", help="Task to generate command for")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive natural language mode")
    parser.add_argument("--verbose", action="store_true", help="Show command explanations (for direct command generation only)")
    parser.add_argument("--history", action="store_true", help="Show command history")
    parser.add_argument("--reuse", type=str, help="Reuse command from history by index")
    parser.add_argument("--add-alias", nargs=2, metavar=("NAME", "TASK"), help="Add an alias for a task")
    parser.add_argument("--remove-alias", type=str, help="Remove an alias")
    parser.add_argument("--list-aliases", action="store_true", help="List all aliases")
    parser.add_argument("--help", action="store_true", help="Show this detailed help")
    parser.add_argument("--set-api-key", type=str, help="Set the Google API key interactively")
    parser.add_argument("--setup", action="store_true", help="Interactive setup for API key and model")
    
    try:
        args = parser.parse_args()
    except SystemExit:
        print_help()
        return

    if args.help:
        print_help()
        return

    if args.setup:
        set_api_key()
        return

    if args.set_api_key:
        set_api_key(args.set_api_key)
        return

    if args.add_alias or args.remove_alias or args.list_aliases:
        manage_aliases(args)
        return

    if args.history:
        history = load_history()
        if not history:
            print(f"{ANSI_RED}No command history found.{ANSI_RESET}")
        else:
            print(f"{ANSI_BLUE}Command History:{ANSI_RESET}")
            for i, entry in enumerate(history):
                print(f"{ANSI_BLUE}{i}: {ANSI_GREEN}{entry['command']}{ANSI_RESET} (Task: {entry['input']})")
        return

    if args.reuse:
        command, user_input = get_history_command(args.reuse)
        if command:
            print(f"{ANSI_BLUE}Reusing Command:{ANSI_RESET}")
            print(f"{ANSI_GREEN}{command}{ANSI_RESET}")
            print(ANSI_SEPARATOR)
            success, error = run_command_normal(command, args.verbose)
            if success:
                print(f"{ANSI_GREEN}Success{ANSI_RESET}")
                show_changes()
            else:
                print(f"{ANSI_RED}{error}{ANSI_RESET}")
        else:
            print(f"{ANSI_RED}Invalid history index.{ANSI_RESET}")
        return

    if args.interactive:
        if create_new_terminal_window():
            return
        else:
            nl_terminal(verbose=args.verbose)
        return

    user_input = " ".join(args.task) if args.task else ""
    if not user_input:
        print_help()
        sys.exit(1)
    
    if config["aliases"].get(user_input):
        user_input = config["aliases"][user_input]
    
    try:
        validated_input = validate_input(user_input)
    except ValidationError as e:
        print(f"{ANSI_RED}Invalid input: {e}{ANSI_RESET}")
        sys.exit(1)
    
    command, explanation = generate_command(validated_input, verbose=args.verbose)
    print(f"{ANSI_BLUE}Command:{ANSI_RESET}")
    print(f"{ANSI_GREEN}{command}{ANSI_RESET}")
    if args.verbose and explanation:
        print(f"{ANSI_BLUE}Explanation:{ANSI_RESET}")
        print(f"{ANSI_CYAN}{explanation}{ANSI_RESET}")
    print(ANSI_SEPARATOR)

    if command.startswith(f"{ANSI_RED}Error:"):
        print(command)
        return

    save_history(validated_input, command)
    success, error = run_command_normal(command, args.verbose)
    if success:
        print(f"{ANSI_GREEN}Success{ANSI_RESET}")
        show_changes()
    else:
        print(f"{ANSI_RED}{error}{ANSI_RESET}")
        if args.verbose:
            explanation = get_error_explanation(error)
            print(f"{ANSI_BLUE}Error Explanation:{ANSI_RESET}")
            print(f"{ANSI_CYAN}{explanation}{ANSI_RESET}")
        print(f"{ANSI_BLUE}Generating alternative...{ANSI_RESET}")
        new_command, new_explanation = generate_command(validated_input, error, args.verbose)
        print(f"{ANSI_BLUE}New Command:{ANSI_RESET}")
        print(f"{ANSI_GREEN}{new_command}{ANSI_RESET}")
        if args.verbose and new_explanation:
            print(f"{ANSI_BLUE}Explanation:{ANSI_RESET}")
            print(f"{ANSI_CYAN}{new_explanation}{ANSI_RESET}")
        print(ANSI_SEPARATOR)
        if new_command.startswith(f"{ANSI_RED}Error:"):
            print(new_command)
            return
        save_history(validated_input, new_command)
        success, error = run_command_normal(new_command, args.verbose)
        if success:
            print(f"{ANSI_GREEN}Success{ANSI_RESET}")
            show_changes()
        else:
            print(f"{ANSI_RED}{error}{ANSI_RESET}")

def set_api_key(api_key: Optional[str] = None) -> None:
    
    try:
        if api_key is None:
            print(f"{ANSI_CYAN}Setting up Google API Key for LinAIx{ANSI_RESET}")
            print(f"{ANSI_YELLOW}1. Get your API key from: https://aistudio.google.com/app/apikey{ANSI_RESET}")
            print(f"{ANSI_YELLOW}2. Enter your API key below:{ANSI_RESET}")
            api_key = input(f"{ANSI_GREEN}API Key: {ANSI_RESET}").strip()
            
            if not api_key:
                print(f"{ANSI_RED}No API key provided. Setup cancelled.{ANSI_RESET}")
                return
        
        if not api_key or len(api_key) < 10:
            print(f"{ANSI_RED}Invalid API key format.{ANSI_RESET}")
            return
        
        
        print(f"{ANSI_CYAN}Available models:{ANSI_RESET}")
        print(f"{ANSI_GREEN}1. gemini-1.5-flash (fast, good for most tasks){ANSI_RESET}")
        print(f"{ANSI_GREEN}2. gemini-1.5-pro (more capable, slower){ANSI_RESET}")
        print(f"{ANSI_GREEN}3. gemini-pro (legacy model){ANSI_RESET}")
        
        model_choice = input(f"{ANSI_YELLOW}Choose model (1-3, default: 1): {ANSI_RESET}").strip()
        
        model_map = {
            "1": "gemini-1.5-flash",
            "2": "gemini-1.5-pro", 
            "3": "gemini-pro"
        }
        
        selected_model = model_map.get(model_choice, "gemini-1.5-flash")
        
        try:
            current_config = load_config()
        except SystemExit:
            current_config = DEFAULT_CONFIG.copy()
        
        current_config["api_key"] = api_key
        current_config["model"] = selected_model
        
        save_config(current_config)
        
        print(f"{ANSI_GREEN}✓ API key and model configured successfully!{ANSI_RESET}")
        print(f"{ANSI_CYAN}Model: {selected_model}{ANSI_RESET}")
        print(f"{ANSI_CYAN}Config saved to: {CONFIG_FILE}{ANSI_RESET}")
        
    except Exception as e:
        logger.error(f"Failed to set API key: {e}")
        print(f"{ANSI_RED}Error: Failed to set API key: {e}{ANSI_RESET}")

def manage_aliases(args: argparse.Namespace) -> None:
   
    try:
        current_config = load_config()
        
        if args.add_alias:
            name, task = args.add_alias
            if not name or not task:
                print(f"{ANSI_RED}Alias name and task cannot be empty{ANSI_RESET}")
                return
            
            try:
                validate_input(task)
            except ValidationError as e:
                print(f"{ANSI_RED}Invalid task: {e}{ANSI_RESET}")
                return
            
            current_config["aliases"][name] = task
            save_config(current_config)
            print(f"{ANSI_GREEN}✓ Alias '{name}' added for task: '{task}'{ANSI_RESET}")
        
        elif args.remove_alias:
            name = args.remove_alias
            if name in current_config["aliases"]:
                del current_config["aliases"][name]
                save_config(current_config)
                print(f"{ANSI_GREEN}✓ Alias '{name}' removed{ANSI_RESET}")
            else:
                print(f"{ANSI_RED}Alias '{name}' not found{ANSI_RESET}")
        
        elif args.list_aliases:
            if not current_config["aliases"]:
                print(f"{ANSI_YELLOW}No aliases defined{ANSI_RESET}")
            else:
                print(f"{ANSI_BLUE}Defined Aliases:{ANSI_RESET}")
                for name, task in current_config["aliases"].items():
                    print(f"{ANSI_GREEN}{name}{ANSI_RESET}: {ANSI_CYAN}{task}{ANSI_RESET}")
                    
    except Exception as e:
        logger.error(f"Failed to manage aliases: {e}")
        print(f"{ANSI_RED}Error: Failed to manage aliases: {e}{ANSI_RESET}")

def create_new_terminal_window() -> bool:
    
    try:
        script_path = Path(__file__).parent / "linaix_nl_terminal.py"
        if not script_path.exists():
            logger.error("linaix_nl_terminal.py does not exist")
            print(f"{ANSI_RED}Could not find linaix_nl_terminal.py!{ANSI_RESET}")
            return False
        current_dir = os.getcwd()
        terminal_commands = [
            [
                "gnome-terminal",
                "--",
                "bash",
                "-c",
                f"cd '{current_dir}' && python3 '{script_path}' ; exec bash"
            ],
            [
                "gnome-terminal",
                "--working-directory", current_dir,
                "--",
                "python3",
                str(script_path)
            ]
        ]
        for i, cmd in enumerate(terminal_commands, 1):
            try:
                logger.info(f"Trying GNOME terminal method {i}: {' '.join(cmd)}")
                process = subprocess.Popen(
                    cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(0.5)
                if process.poll() is None:
                    print(f"{ANSI_GREEN}✓ Opening LinAIx NL Terminal in a new GNOME terminal window...{ANSI_RESET}")
                    logger.info(f"Successfully opened GNOME terminal with method {i}")
                    return True
            except Exception as e:
                logger.warning(f"GNOME terminal method {i} failed: {e}")
                continue
        print(f"{ANSI_RED}Could not open GNOME terminal. Running in current terminal.{ANSI_RESET}")
        return False
    except Exception as e:
        logger.error(f"Failed to create new terminal window: {e}")
        print(f"{ANSI_RED}Error creating new terminal window: {e}{ANSI_RESET}")
        return False

if __name__ == "__main__":
    main() 
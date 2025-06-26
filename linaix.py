#!/usr/bin/env python3
import sys
import os
import google.generativeai as genai
import re
import json
import time
import subprocess
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
import argparse
import platform
import shutil

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

# Constants for prompt_toolkit Colors
PTK_GREEN = "ansigreen"
PTK_RED = "ansired"
PTK_YELLOW = "ansiyellow"
PTK_BLUE = "ansiblue"
PTK_CYAN = "ansicyan"
PTK_MAGENTA = "ansimagenta"

# Constants for Style
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

DIRECT_COMMANDS = ['cd', 'ls', 'pwd', 'mkdir', 'touch', 'rm', 'cat', 'echo']

DESTRUCTIVE_COMMANDS = ['rm', 'dd', 'chmod', 'chown', 'mkfs']

HISTORY_LIMIT = 100

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "gemini-1.5-flash",
    "auto_run_safe": False,
    "aliases": {}
}

def load_config():
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir()
    if not CONFIG_FILE.exists() or CONFIG_FILE.stat().st_size == 0:
        with CONFIG_FILE.open("w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    try:
        with CONFIG_FILE.open("r") as f:
            config = json.load(f)
    except json.JSONDecodeError:
        with CONFIG_FILE.open("w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        config = DEFAULT_CONFIG.copy()
    if not config["api_key"] and "GOOGLE_API_KEY" in os.environ:
        config["api_key"] = os.environ["GOOGLE_API_KEY"]
    if not config["api_key"]:
        print(f"{ANSI_RED}Error: No Google API key found. Set it in {CONFIG_FILE} or export GOOGLE_API_KEY.{ANSI_RESET}")
        sys.exit(1)
    return config

def save_config(config):
    with CONFIG_FILE.open("w") as f:
        json.dump(config, f, indent=2)

def save_history(user_input, command):
    history = []
    if HISTORY_FILE.exists():
        with HISTORY_FILE.open("r") as f:
            history = json.load(f)
    history.append({"input": user_input, "command": command})
    with HISTORY_FILE.open("w") as f:
        json.dump(history[-HISTORY_LIMIT:], f, indent=2)

def load_history():
    if HISTORY_FILE.exists():
        with HISTORY_FILE.open("r") as f:
            return json.load(f)
    return []

def get_history_command(index):
    history = load_history()
    try:
        return history[int(index)]["command"], history[int(index)]["input"]
    except (IndexError, ValueError):
        return None, None

def get_autocomplete_suggestions():
    history = load_history()
    return [entry["input"] for entry in history]

config = load_config()
genai.configure(api_key=config["api_key"])

def generate_command(user_input, error_context=None, verbose=False):
    try:
        model = genai.GenerativeModel(config["model"])
        current_dir = os.getcwd()
        prompt = f"Generate a single, safe, correct Linux command for a Debian-based system to: {user_input}. Current directory: {current_dir}. Return only the command, no explanations."
        if error_context:
            prompt += f" Previous command failed with error: '{error_context}'. Suggest a corrected command."
        if verbose:
            prompt += " Additionally, return a brief explanation in the format: [EXPLANATION: ...]"
        response = model.generate_content(prompt)
        text = response.text.strip()
        command = re.sub(r'```bash\n|```|\n\[EXPLANATION:.*', '', text).strip()
        explanation = re.search(r'\[EXPLANATION: (.*?)\]', text)
        explanation = explanation.group(1) if explanation else ""
        return command if command else f"{ANSI_RED}Error: No valid command generated.{ANSI_RESET}", explanation
    except Exception as e:
        return f"{ANSI_RED}Error: Could not generate command: {str(e)}{ANSI_RESET}", ""

def get_error_explanation(error):
    try:
        model = genai.GenerativeModel(config["model"])
        response = model.generate_content(f"Explain this Linux command error briefly: '{error}'")
        return response.text.strip()
    except Exception:
        return f"{ANSI_RED}Unable to explain error.{ANSI_RESET}"

def simulate_typing(command):
    print(f"{ANSI_BLUE}Executing command:{ANSI_RESET} ", end="", flush=True)
    for char in command:
        print(char, end="", flush=True)
        time.sleep(0.05)
    print()

def run_command_interactive(command, verbose=False):
    if command.strip().startswith("cd "):
        try:
            new_dir = command.strip().split(" ", 1)[1]
            os.chdir(os.path.expanduser(new_dir))
            print(f"{ANSI_GREEN}Changed directory to: {os.getcwd()}{ANSI_RESET}")
            return True, ""
        except Exception as e:
            return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

    simulate_typing(command)

    try:
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        if result.stdout:
            print(f"{ANSI_CYAN}Output:{ANSI_RESET}")
            print(result.stdout.strip())
        if result.stderr:
            print(f"{ANSI_RED}Error:{ANSI_RESET}")
            print(result.stderr.strip())
        return result.returncode == 0, result.stderr.strip()
    except Exception as e:
        return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

def run_command_normal(command, verbose=False):
    if command.strip().startswith("cd "):
        try:
            new_dir = command.strip().split(" ", 1)[1]
            os.chdir(os.path.expanduser(new_dir))
            print(f"{ANSI_GREEN}Changed directory to: {os.getcwd()}{ANSI_RESET}")
            return True, ""
        except Exception as e:
            return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

    confirm = input(f"{ANSI_YELLOW}Do you want to execute this command? (y/n): {ANSI_RESET}").strip().lower()
    if confirm in ['y', 'yes']:
        simulate_typing(command)
        try:
            result = subprocess.run(command, shell=True, text=True, capture_output=True)
            if result.stdout:
                print(f"{ANSI_CYAN}Output:{ANSI_RESET}")
                print(result.stdout.strip())
            if result.stderr:
                print(f"{ANSI_RED}Error:{ANSI_RESET}")
                print(result.stderr.strip())
            return result.returncode == 0, result.stderr.strip()
        except Exception as e:
            return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"
    else:
        print(f"{ANSI_YELLOW}Command not executed.{ANSI_RESET}")
        sys.exit(0)
        
def show_changes():
    print(f"{ANSI_BLUE}Current Directory: {os.getcwd()}{ANSI_RESET}")
    try:
        result = subprocess.run("ls -l", shell=True, text=True, capture_output=True)
        if result.stdout:
            print(f"{ANSI_CYAN}Directory Contents:{ANSI_RESET}")
            print(result.stdout.strip())
        if result.stderr:
            print(f"{ANSI_RED}Error listing directory:{ANSI_RESET}")
            print(result.stderr.strip())
    except Exception as e:
        print(f"{ANSI_RED}Error listing directory: {str(e)}{ANSI_RESET}")

def is_destructive_command(command):
    return any(cmd in command.lower() for cmd in DESTRUCTIVE_COMMANDS)

def print_help():
    print(f"{ANSI_MAGENTA}{'-' * 60}{ANSI_RESET}")
    print(f"{ANSI_MAGENTA}LinAIx: Linux Command Assistant powered by Gemini API{ANSI_RESET}")
    print(f"{ANSI_MAGENTA}{'-' * 60}{ANSI_RESET}")
    print(f"{ANSI_BLUE}Usage:{ANSI_RESET} linaix [options] 'task description'")
    print(f"\n{ANSI_BLUE}Options:{ANSI_RESET}")
    print(f"  {ANSI_GREEN}'task'{ANSI_RESET}            Generate a command for the task (e.g., 'create a python file test.py')")
    print(f"  {ANSI_GREEN}--interactive{ANSI_RESET}     Open a new terminal for natural language mode (AI shell)")
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
    print(f"  linaix --interactive                   # Opens natural language AI shell in a new terminal")
    print(f"  linaix --add-alias listpy 'list all python files'  # Adds alias")
    print(f"  linaix listpy                          # Uses alias and prompts")
    print(f"\n{ANSI_BLUE}Setup:{ANSI_RESET}")
    print(f"  1. Run: {ANSI_GREEN}linaix --setup{ANSI_RESET} for interactive setup")
    print(f"  2. Or obtain a Google API key from https://aistudio.google.com/app/apikey")
    print(f"  3. Set it in {CONFIG_FILE} or export GOOGLE_API_KEY='your-api-key'")
    print(f"{ANSI_MAGENTA}{'-' * 60}{ANSI_RESET}")

def print_centered(text, color=""):
    width = shutil.get_terminal_size((80, 20)).columns
    for line in text.splitlines():
        if line.strip() == "":
            print()
        else:
            print(color + line.center(width) + ANSI_RESET)

def print_linaix_banner():
    banner = f"""
██╗     ██╗███╗   ██╗ █████╗ ██╗██╗  ██╗
██║     ██║████╗  ██║██╔══██╗██║╚██╗██╔╝
██║     ██║██╔██╗ ██║███████║██║ ╚███╔╝ 
██║     ██║██║╚██╗██║██╔══██║██║ ██╔██╗ 
███████╗██║██║ ╚████║██║  ██║██║██╔╝ ██╗
╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
"""
    print_centered(banner, ANSI_GREEN + ANSI_BOLD)

def print_intro():
    width = shutil.get_terminal_size((80, 20)).columns
    border = "+" + ("-" * (width - 2)) + "+"
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

def nl_terminal(verbose=False):
    print_linaix_banner()
    print_intro()
    while True:
        try:
            user = os.getenv('USER') or os.getenv('USERNAME') or 'user'
            host = os.uname().nodename if hasattr(os, 'uname') else 'host'
            cwd = os.getcwd()
            short_cwd = os.path.basename(cwd) or '/'
            prompt = f"{ANSI_GREEN}{user}@{host}{ANSI_RESET}:{ANSI_BLUE}{cwd}{ANSI_RESET} $ "
            user_input = input(prompt).strip()
            if not user_input:
                continue
            if user_input.lower() in ['exit', 'quit']:
                print(f"{ANSI_GREEN}Goodbye!{ANSI_RESET}")
                break
            command, explanation = generate_command(user_input, verbose=verbose)
            if not command:
                print(f"{ANSI_RED}Could not generate a command for your request.{ANSI_RESET}")
                continue
            print(f"{ANSI_BLUE}Generated Command:{ANSI_RESET} {ANSI_GREEN}{command}{ANSI_RESET}")
            if verbose and explanation:
                print(f"{ANSI_BLUE}Explanation:{ANSI_RESET} {ANSI_CYAN}{explanation}{ANSI_RESET}")
            success, error = run_command_interactive(command)
            if success:
                print(f"{ANSI_GREEN}✓ Success{ANSI_RESET}")
            else:
                print(f"{ANSI_RED}✗ Error: {error}{ANSI_RESET}")
        except (EOFError, KeyboardInterrupt):
            print(f"\n{ANSI_GREEN}Goodbye!{ANSI_RESET}")
            break

def create_new_terminal_window():
    """Create a new terminal window/tab for interactive mode"""
    script_path = Path(__file__).resolve()
    
    if platform.system() == "Windows":
        # Windows: Use start command to open new window
        try:
            subprocess.run([
                "start", "cmd", "/k", 
                f"python \"{script_path}\" --interactive"
            ], shell=True, check=True)
            print(f"{ANSI_GREEN}✓ Opening LinAIx in a new terminal window...{ANSI_RESET}")
            return True
        except subprocess.CalledProcessError:
            print(f"{ANSI_RED}Failed to open new terminal window. Running in current terminal.{ANSI_RESET}")
            return False
    elif platform.system() == "Darwin":  # macOS
        # macOS: Use osascript to open new terminal
        try:
            script = f'''
            tell application "Terminal"
                do script "cd '{os.getcwd()}' && python3 '{script_path}' --interactive"
                activate
            end tell
            '''
            subprocess.run(["osascript", "-e", script], check=True)
            print(f"{ANSI_GREEN}✓ Opening LinAIx in a new terminal window...{ANSI_RESET}")
            return True
        except subprocess.CalledProcessError:
            print(f"{ANSI_RED}Failed to open new terminal window. Running in current terminal.{ANSI_RESET}")
            return False
    else:  # Linux
        # Linux: Try different terminal emulators
        terminals = [
            ("gnome-terminal", ["gnome-terminal", "--", "python3", str(script_path), "--interactive"]),
            ("konsole", ["konsole", "-e", f"python3 {script_path} --interactive"]),
            ("xterm", ["xterm", "-e", f"python3 {script_path} --interactive"]),
            ("terminator", ["terminator", "-e", f"python3 {script_path} --interactive"]),
        ]
        
        for term_name, cmd in terminals:
            try:
                subprocess.run(cmd, check=True)
                print(f"{ANSI_GREEN}✓ Opening LinAIx in a new {term_name} window...{ANSI_RESET}")
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        print(f"{ANSI_RED}Could not open new terminal window. Running in current terminal.{ANSI_RESET}")
        return False

def main():
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
    args = parser.parse_args()

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
        # Try to create a new terminal window, fallback to current terminal
        if not create_new_terminal_window():
            nl_terminal(verbose=args.verbose)
        return

    user_input = " ".join(args.task) if args.task else ""
    if not user_input:
        print_help()
        sys.exit(1)
    if config["aliases"].get(user_input):
        user_input = config["aliases"][user_input]
    command, explanation = generate_command(user_input, verbose=args.verbose)
    print(f"{ANSI_BLUE}Command:{ANSI_RESET}")
    print(f"{ANSI_GREEN}{command}{ANSI_RESET}")
    if args.verbose and explanation:
        print(f"{ANSI_BLUE}Explanation:{ANSI_RESET}")
        print(f"{ANSI_CYAN}{explanation}{ANSI_RESET}")
    print(ANSI_SEPARATOR)

    if "Error" in command:
        print(command)
        return

    save_history(user_input, command)
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
        new_command, new_explanation = generate_command(user_input, error, args.verbose)
        print(f"{ANSI_BLUE}New Command:{ANSI_RESET}")
        print(f"{ANSI_GREEN}{new_command}{ANSI_RESET}")
        if args.verbose and new_explanation:
            print(f"{ANSI_BLUE}Explanation:{ANSI_RESET}")
            print(f"{ANSI_CYAN}{new_explanation}{ANSI_RESET}")
        print(ANSI_SEPARATOR)
        if "Error" in new_command:
            print(new_command)
            return
        save_history(user_input, new_command)
        success, error = run_command_normal(new_command, args.verbose)
        if success:
            print(f"{ANSI_GREEN}Success{ANSI_RESET}")
            show_changes()
        else:
            print(f"{ANSI_RED}{error}{ANSI_RESET}")

def set_api_key(api_key=None):
    """Set the API key interactively or via parameter"""
    if api_key is None:
        print(f"{ANSI_CYAN}Setting up Google API Key for LinAIx{ANSI_RESET}")
        print(f"{ANSI_YELLOW}1. Get your API key from: https://aistudio.google.com/app/apikey{ANSI_RESET}")
        print(f"{ANSI_YELLOW}2. Enter your API key below:{ANSI_RESET}")
        api_key = input(f"{ANSI_GREEN}API Key: {ANSI_RESET}").strip()
        
        if not api_key:
            print(f"{ANSI_RED}No API key provided. Setup cancelled.{ANSI_RESET}")
            return
    
    # Get model preference
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
    
    # Load current config or create new one
    config = {}
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r") as f:
                config = json.load(f)
        except:
            config = DEFAULT_CONFIG
    else:
        config = DEFAULT_CONFIG
    
    # Update config
    config["api_key"] = api_key
    config["model"] = selected_model
    
    # Save config
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir()
    
    with CONFIG_FILE.open("w") as f:
        json.dump(config, f, indent=2)
    
    print(f"{ANSI_GREEN}✓ API key and model configured successfully!{ANSI_RESET}")
    print(f"{ANSI_CYAN}Model: {selected_model}{ANSI_RESET}")
    print(f"{ANSI_CYAN}Config saved to: {CONFIG_FILE}{ANSI_RESET}")

def manage_aliases(args):
    """Manage aliases for the linaix command"""
    config = load_config()
    
    if args.add_alias:
        name, task = args.add_alias
        config["aliases"][name] = task
        save_config(config)
        print(f"{ANSI_GREEN}✓ Alias '{name}' added for task: '{task}'{ANSI_RESET}")
    
    elif args.remove_alias:
        name = args.remove_alias
        if name in config["aliases"]:
            del config["aliases"][name]
            save_config(config)
            print(f"{ANSI_GREEN}✓ Alias '{name}' removed{ANSI_RESET}")
        else:
            print(f"{ANSI_RED}Alias '{name}' not found{ANSI_RESET}")
    
    elif args.list_aliases:
        if not config["aliases"]:
            print(f"{ANSI_YELLOW}No aliases defined{ANSI_RESET}")
        else:
            print(f"{ANSI_BLUE}Defined Aliases:{ANSI_RESET}")
            for name, task in config["aliases"].items():
                print(f"{ANSI_GREEN}{name}{ANSI_RESET}: {ANSI_CYAN}{task}{ANSI_RESET}")

if __name__ == "__main__":
    main()

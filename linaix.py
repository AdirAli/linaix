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

# Constants for Paths
CONFIG_DIR = Path.home() / ".linaix"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

# Constants for Default Configuration
DEFAULT_CONFIG = {
    "api_key": "",
    "model": "gemini-1.5-flash",
    "auto_run_safe": False,
    "aliases": {}
}

# Constants for ANSI Colors (for print statements)
ANSI_GREEN = "\033[1;32m"
ANSI_RED = "\033[1;31m"
ANSI_YELLOW = "\033[1;33m"
ANSI_BLUE = "\033[1;34m"
ANSI_CYAN = "\033[1;36m"
ANSI_MAGENTA = "\033[1;35m"
ANSI_RESET = "\033[0m"
ANSI_SEPARATOR = "\033[1;34m" + "-" * 40 + "\033[0m"

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

# Constants for Direct Commands
DIRECT_COMMANDS = ['cd', 'ls', 'pwd', 'mkdir', 'touch', 'rm', 'cat', 'echo']

# Constants for Destructive Commands
DESTRUCTIVE_COMMANDS = ['rm', 'dd', 'chmod', 'chown', 'mkfs']

# Constants for History Limit
HISTORY_LIMIT = 100

def load_config():
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir()
    if not CONFIG_FILE.exists():
        with CONFIG_FILE.open("w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    with CONFIG_FILE.open("r") as f:
        config = json.load(f)

    if not config["api_key"] and "GOOGLE_API_KEY" in os.environ:
        config["api_key"] = os.environ["GOOGLE_API_KEY"]
    if not config["api_key"]:
        print(f"{ANSI_RED}Error: No Google API key found. Set it with one of these options:{ANSI_RESET}")
        print(f"  1. Edit {CONFIG_FILE} with your API key.")
        print(f"  2. Run: {ANSI_BLUE}linaix --set-api-key 'your-api-key'{ANSI_RESET}")
        print(f"  3. Export: {ANSI_BLUE}export GOOGLE_API_KEY='your-api-key'{ANSI_RESET}")
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
        return False, "Command execution skipped by user"

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

def interactive_mode(first_time=True):
    if first_time:
        print(f"{ANSI_MAGENTA}{'-' * 50}{ANSI_RESET}")
        print(f"{ANSI_MAGENTA}Welcome to LinAIx Interactive Mode!{ANSI_RESET}")
        print(f"{ANSI_CYAN}- Enter tasks (e.g., 'make a new file') or Linux commands (e.g., 'ls', 'cd /tmp'){ANSI_RESET}")
        print(f"{ANSI_CYAN}- Use TAB for autocomplete based on history{ANSI_RESET}")
        print(f"{ANSI_CYAN}- Press Ctrl+D to exit{ANSI_RESET}")
        print(f"{ANSI_MAGENTA}{'-' * 50}{ANSI_RESET}")
        show_changes()

    completer = WordCompleter(get_autocomplete_suggestions(), ignore_case=True)
    session = PromptSession("\n🌟 LinAIx> ", completer=completer, style=STYLE)
    command_count = 0
    while True:
        try:
            user_input = session.prompt()
            if not user_input:
                continue
            command_count += 1
            print(f"{ANSI_BLUE}[Task {command_count}]{ANSI_RESET}")

            if user_input.strip().split()[0].lower() in DIRECT_COMMANDS:
                command = user_input
            else:
                if config["aliases"].get(user_input):
                    user_input = config["aliases"][user_input]
                command, explanation = generate_command(user_input, verbose=False)
                if "Error" in command:
                    print(command)
                    continue
                print(f"{ANSI_BLUE}Generated Command:{ANSI_RESET} {ANSI_GREEN}{command}{ANSI_RESET}")

            if is_destructive_command(command) and not config["auto_run_safe"]:
                confirm = input(f"{ANSI_RED}Destructive command detected. Confirm? (y/n):{ANSI_RESET} ").strip().lower()
                if confirm not in ['y', 'yes']:
                    print(f"{ANSI_RED}Not executed.{ANSI_RESET}")
                    continue

            success, error = run_command_interactive(command, verbose=False)
            save_history(user_input, command)

            if success:
                print(f"{ANSI_GREEN}Success{ANSI_RESET}")
                show_changes()
            else:
                print(f"{ANSI_RED}Error: {error}{ANSI_RESET}")
                new_command, new_explanation = generate_command(user_input, error, verbose=False)
                if "Error" in new_command:
                    print(new_command)
                    continue
                print(f"{ANSI_BLUE}Alternative Command:{ANSI_RESET} {ANSI_GREEN}{new_command}{ANSI_RESET}")
                if is_destructive_command(new_command) and not config["auto_run_safe"]:
                    confirm = input(f"{ANSI_RED}Destructive command detected. Confirm? (y/n):{ANSI_RESET} ").strip().lower()
                    if confirm not in ['y', 'yes']:
                        print(f"{ANSI_RED}Not executed.{ANSI_RESET}")
                        continue
                success, error = run_command_interactive(new_command, verbose=False)
                save_history(user_input, new_command)
                if success:
                    print(f"{ANSI_GREEN}Success{ANSI_RESET}")
                    show_changes()
                else:
                    print(f"{ANSI_RED}Error: {error}{ANSI_RESET}")

        except EOFError:
            print(f"\n{ANSI_RED}Exiting interactive mode.{ANSI_RESET}")
            print(f"{ANSI_MAGENTA}" + "=" * 50 + "{ANSI_RESET}")
            sys.exit(0)

def print_help():
    print(f"{ANSI_MAGENTA}{'-' * 60}{ANSI_RESET}")
    print(f"{ANSI_MAGENTA}LinAIx: Linux Command Assistant powered by Gemini API{ANSI_RESET}")
    print(f"{ANSI_MAGENTA}{'-' * 60}{ANSI_RESET}")
    print(f"{ANSI_BLUE}Usage:{ANSI_RESET} linaix [options] 'task description'")
    print(f"\n{ANSI_BLUE}Options:{ANSI_RESET}")
    print(f"  {ANSI_GREEN}'task'{ANSI_RESET}            Generate a command for the task (e.g., 'create a python file test.py')")
    print(f"  {ANSI_GREEN}--interactive{ANSI_RESET}     Enter interactive mode with dynamic terminal experience")
    print(f"  {ANSI_GREEN}--verbose{ANSI_RESET}         Show command and error explanations")
    print(f"  {ANSI_GREEN}--history{ANSI_RESET}         Display command history")
    print(f"  {ANSI_GREEN}--reuse <index>{ANSI_RESET}   Reuse a command from history by index")
    print(f"  {ANSI_GREEN}--add-alias <name> <task>{ANSI_RESET}  Add an alias (e.g., 'listpy' 'list all python files')")
    print(f"  {ANSI_GREEN}--remove-alias <name>{ANSI_RESET}     Remove an alias")
    print(f"  {ANSI_GREEN}--list-aliases{ANSI_RESET}         List all aliases")
    print(f"  {ANSI_GREEN}--help{ANSI_RESET}            Show this detailed help")
    print(f"\n{ANSI_BLUE}Examples:{ANSI_RESET}")
    print(f"  linaix 'list all python files'          # Generates 'ls *.py' and prompts for execution")
    print(f"  linaix --verbose 'create a directory'   # Includes explanation and prompts")
    print(f"  linaix --interactive                    # Interactive mode with live terminal experience")
    print(f"  linaix --add-alias listpy 'list all python files'  # Adds alias")
    print(f"  linaix listpy                          # Uses alias and prompts")
    print(f"\n{ANSI_BLUE}Setup:{ANSI_RESET}")
    print(f"  1. Obtain a Google API key from https://aistudio.google.com/app/apikey")
    print(f"  2. Set it in {CONFIG_FILE} or export GOOGLE_API_KEY='your-api-key'")
    print(f"{ANSI_MAGENTA}{'-' * 60}{ANSI_RESET}")

def manage_aliases(args):
    if args.add_alias:
        config["aliases"][args.add_alias[0]] = args.add_alias[1]
        save_config(config)
        print(f"{ANSI_GREEN}Alias '{args.add_alias[0]}' added for task: {args.add_alias[1]}{ANSI_RESET}")
    elif args.remove_alias:
        if args.remove_alias in config["aliases"]:
            del config["aliases"][args.remove_alias]
            save_config(config)
            print(f"{ANSI_GREEN}Alias '{args.remove_alias}' removed.{ANSI_RESET}")
        else:
            print(f"{ANSI_RED}Alias '{args.remove_alias}' not found.{ANSI_RESET}")
    elif args.list_aliases:
        if config["aliases"]:
            print(f"{ANSI_BLUE}Aliases:{ANSI_RESET}")
            for alias, task in config["aliases"].items():
                print(f"{ANSI_GREEN}{alias}{ANSI_RESET}: {task}")
        else:
            print(f"{ANSI_RED}No aliases defined.{ANSI_RESET}")

def set_api_key(api_key):
    config["api_key"] = api_key
    save_config(config)
    print(f"{ANSI_GREEN}API key set successfully.{ANSI_RESET}")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="Linux Command Assistant", add_help=False)
    parser.add_argument("task", nargs="*", help="Task to generate command for")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--verbose", action="store_true", help="Show command explanations")
    parser.add_argument("--history", action="store_true", help="Show command history")
    parser.add_argument("--reuse", type=str, help="Reuse command from history by index")
    parser.add_argument("--add-alias", nargs=2, metavar=("NAME", "TASK"), help="Add an alias for a task")
    parser.add_argument("--remove-alias", type=str, help="Remove an alias")
    parser.add_argument("--list-aliases", action="store_true", help="List all aliases")
    parser.add_argument("--help", action="store_true", help="Show this detailed help")
    parser.add_argument("--set-api-key", type=str, help="Set the Google API key interactively")
    args = parser.parse_args()

    if args.help:
        print_help()
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

    user_input = " ".join(args.task) if args.task else ""
    if args.interactive:
        interactive_mode(first_time=True)
    else:
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

if __name__ == "__main__":
    main()

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

# Configuration
CONFIG_DIR = Path.home() / ".linaix"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
DEFAULT_CONFIG = {
    "api_key": "",  # set by user
    "model": "gemini-1.5-flash",
    "auto_run_safe": False,
    "aliases": {}
}

# Styling for interactive mode
style = Style.from_dict({
    'prompt': '#00aa00 bold',
    'output': '#ffffff',
    'command': '#00ff00',
    'explanation': '#55aaff',
    'error': '#ff5555',
    'header': '#aa55ff bold',
    'info': '#00ffff',
    'separator': '#444444',
})

def load_config():
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir()
    if not CONFIG_FILE.exists():
        with CONFIG_FILE.open("w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    with CONFIG_FILE.open("r") as f:
        config = json.load(f)
    # Check for API key in environment variable as fallback
    if not config["api_key"] and "GOOGLE_API_KEY" in os.environ:
        config["api_key"] = os.environ["GOOGLE_API_KEY"]
    if not config["api_key"]:
        print("\033[1;31mError: No Google API key found. Please set it in ~/.linaix/config.json or export GOOGLE_API_KEY.\033[0m")
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
        json.dump(history[-100:], f, indent=2)

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

# Initialize Gemini
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
        return command if command else "Error: No valid command generated.", explanation
    except Exception as e:
        return f"Error: Could not generate command: {str(e)}", ""

def get_error_explanation(error):
    try:
        model = genai.GenerativeModel(config["model"])
        response = model.generate_content(f"Explain this Linux command error briefly: '{error}'")
        return response.text.strip()
    except Exception:
        return "Unable to explain error."

def simulate_typing(command):
    print("\033[1;34mExecuting command:\033[0m ", end="", flush=True)
    for char in command:
        print(char, end="", flush=True)
        time.sleep(0.05)  # Simulate typing delay
    print()  # New line after command

def run_command_interactive(command, verbose=False):
    # Handle 'cd' commands manually to change the Python process's directory
    if command.strip().startswith("cd "):
        try:
            new_dir = command.strip().split(" ", 1)[1]
            os.chdir(os.path.expanduser(new_dir))
            print(f"\033[1;32mChanged directory to: {os.getcwd()}\033[0m")
            return True, ""
        except Exception as e:
            return False, f"Error: {str(e)}"

    # Simulate typing the command
    simulate_typing(command)

    # Execute the command using subprocess
    try:
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        if result.stdout:
            print("\033[1;36mOutput:\033[0m")
            print(result.stdout.strip())
        if result.stderr:
            print("\033[1;31mError:\033[0m")
            print(result.stderr.strip())
        return result.returncode == 0, result.stderr.strip()
    except Exception as e:
        return False, f"Error: {str(e)}"

def run_command_normal(command, verbose=False):
    # Handle 'cd' commands manually to change the Python process's directory
    if command.strip().startswith("cd "):
        try:
            new_dir = command.strip().split(" ", 1)[1]
            os.chdir(os.path.expanduser(new_dir))
            print(f"\033[1;32mChanged directory to: {os.getcwd()}\033[0m")
            return True, ""
        except Exception as e:
            return False, f"Error: {str(e)}"

    # Prompt user to execute the command
    confirm = input("\033[1;33mDo you want to execute this command? (y/n): \033[0m").strip().lower()
    if confirm in ['y', 'yes']:
        simulate_typing(command)
        try:
            result = subprocess.run(command, shell=True, text=True, capture_output=True)
            if result.stdout:
                print("\033[1;36mOutput:\033[0m")
                print(result.stdout.strip())
            if result.stderr:
                print("\033[1;31mError:\033[0m")
                print(result.stderr.strip())
            return result.returncode == 0, result.stderr.strip()
        except Exception as e:
            return False, f"Error: {str(e)}"
    else:
        print("\033[1;33mCommand not executed.\033[0m")
        return False, "Command execution skipped by user"

def show_changes():
    # Show the current directory and list its contents
    print(f"\033[1;34mCurrent Directory: {os.getcwd()}\033[0m")
    try:
        result = subprocess.run("ls -l", shell=True, text=True, capture_output=True)
        if result.stdout:
            print("\033[1;36mDirectory Contents:\033[0m")
            print(result.stdout.strip())
        if result.stderr:
            print("\033[1;31mError listing directory:\033[0m")
            print(result.stderr.strip())
    except Exception as e:
        print(f"\033[1;31mError listing directory: {str(e)}\033[0m")

def is_destructive_command(command):
    destructive = ['rm', 'dd', 'chmod', 'chown', 'mkfs']
    return any(cmd in command.lower() for cmd in destructive)

def interactive_mode(first_time=True):
    if first_time:
        print("\033[1;35m" + "=" * 50 + "\033[0m")
        print("\033[1;35mWelcome to LinAIx Interactive Mode!\033[0m")
        print("\033[1;36m- Enter tasks (e.g., 'make a new file') or Linux commands (e.g., 'ls', 'cd /tmp')\033[0m")
        print("\033[1;36m- Use TAB for autocomplete based on history\033[0m")
        print("\033[1;36m- Press Ctrl+D to exit\033[0m")
        print("\033[1;35m" + "=" * 50 + "\033[0m")
        show_changes()  # Show initial directory state

    completer = WordCompleter(get_autocomplete_suggestions(), ignore_case=True)
    session = PromptSession("\n🌟 LinAIx> ", completer=completer, style=style)
    command_count = 0
    while True:
        try:
            user_input = session.prompt()
            if not user_input:
                continue
            command_count += 1
            print(f"\033[1;34m[Task {command_count}]\033[0m")

            # Check if the input is a direct Linux command
            direct_commands = ['cd', 'ls', 'pwd', 'mkdir', 'touch', 'rm', 'cat', 'echo']
            first_word = user_input.strip().split()[0].lower()
            if first_word in direct_commands:
                command = user_input
            else:
                # Check for aliases
                if config["aliases"].get(user_input):
                    user_input = config["aliases"][user_input]
                # Generate command via AI
                command, explanation = generate_command(user_input, verbose=False)
                if "Error" in command:
                    print(f"\033[1;31m{command}\033[0m")
                    continue
                print(f"\033[1;34mGenerated Command:\033[0m \033[1;32m{command}\033[0m")

            # Handle destructive commands
            if is_destructive_command(command) and not config["auto_run_safe"]:
                confirm = input("\033[1;31mDestructive command detected. Confirm? (y/n):\033[0m ").strip().lower()
                if confirm not in ['y', 'yes']:
                    print("\033[1;31mNot executed.\033[0m")
                    continue

            # Execute the command
            success, error = run_command_interactive(command, verbose=False)
            save_history(user_input, command)

            # Show changes after execution
            if success:
                print("\033[1;32mSuccess\033[0m")
                show_changes()
            else:
                print(f"\033[1;31mError: {error}\033[0m")
                # Generate alternative if the command failed
                new_command, new_explanation = generate_command(user_input, error, verbose=False)
                if "Error" in new_command:
                    print(f"\033[1;31m{new_command}\033[0m")
                    continue
                print(f"\033[1;34mAlternative Command:\033[0m \033[1;32m{new_command}\033[0m")
                if is_destructive_command(new_command) and not config["auto_run_safe"]:
                    confirm = input("\033[1;31mDestructive command detected. Confirm? (y/n):\033[0m ").strip().lower()
                    if confirm not in ['y', 'yes']:
                        print("\033[1;31mNot executed.\033[0m")
                        continue
                success, error = run_command_interactive(new_command, verbose=False)
                save_history(user_input, new_command)
                if success:
                    print("\033[1;32mSuccess\033[0m")
                    show_changes()
                else:
                    print(f"\033[1;31mError: {error}\033[0m")

        except EOFError:
            print("\n\033[1;31mExiting interactive mode.\033[0m")
            print("\033[1;35m" + "=" * 50 + "\033[0m")
            sys.exit(0)

def print_help():
    print("\033[1;35m" + "=" * 60 + "\033[0m")
    print("\033[1;35mLinAIx: Linux Command Assistant powered by Gemini API\033[0m")
    print("\033[1;35m" + "=" * 60 + "\033[0m")
    print("\033[1;34mUsage:\033[0m linaix [options] 'task description'")
    print("\n\033[1;34mOptions:\033[0m")
    print("  \033[1;32m'task'\033[0m            Generate a command for the task (e.g., 'create a python file test.py')")
    print("  \033[1;32m--interactive\033[0m     Enter interactive mode with dynamic terminal experience")
    print("  \033[1;32m--verbose\033[0m         Show command and error explanations")
    print("  \033[1;32m--history\033[0m         Display command history")
    print("  \033[1;32m--reuse <index>\033[0m   Reuse a command from history by index")
    print("  \033[1;32m--add-alias <name> <task>\033[0m  Add an alias (e.g., 'listpy' 'list all python files')")
    print("  \033[1;32m--remove-alias <name>\033[0m     Remove an alias")
    print("  \033[1;32m--list-aliases\033[0m         List all aliases")
    print("  \033[1;32m--help\033[0m            Show this detailed help")
    print("\n\033[1;34mExamples:\033[0m")
    print("  linaix 'list all python files'          # Generates 'ls *.py' and prompts for execution")
    print("  linaix --verbose 'create a directory'   # Includes explanation and prompts")
    print("  linaix --interactive                    # Interactive mode with live terminal experience")
    print("  linaix --add-alias listpy 'list all python files'  # Adds alias")
    print("  linaix listpy                          # Uses alias and prompts")
    print("\n\033[1;34mSetup:\033[0m")
    print("  1. Obtain a Google API key from https://aistudio.google.com/app/apikey")
    print("  2. Set it in ~/.linaix/config.json or export GOOGLE_API_KEY='your-api-key'")
    print("\033[1;35m" + "=" * 60 + "\033[0m")

def manage_aliases(args):
    if args.add_alias:
        config["aliases"][args.add_alias[0]] = args.add_alias[1]
        save_config(config)
        print(f"\033[1;32mAlias '{args.add_alias[0]}' added for task: {args.add_alias[1]}\033[0m")
    elif args.remove_alias:
        if args.remove_alias in config["aliases"]:
            del config["aliases"][args.remove_alias]
            save_config(config)
            print(f"\033[1;32mAlias '{args.remove_alias}' removed.\033[0m")
        else:
            print(f"\033[1;31mAlias '{args.remove_alias}' not found.\033[0m")
    elif args.list_aliases:
        if config["aliases"]:
            print("\033[1;34mAliases:\033[0m")
            for alias, task in config["aliases"].items():
                print(f"\033[1;32m{alias}\033[0m: {task}")
        else:
            print("\033[1;31mNo aliases defined.\033[0m")

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
    parser.add_argument("-h", "--help", action="store_true", help="Show this detailed help")
    args = parser.parse_args()

    if args.help:
        print_help()
        return

    if args.add_alias or args.remove_alias or args.list_aliases:
        manage_aliases(args)
        return

    if args.history:
        history = load_history()
        if not history:
            print("\033[1;31mNo command history found.\033[0m")
        else:
            print("\033[1;34mCommand History:\033[0m")
            for i, entry in enumerate(history):
                print(f"\033[1;34m{i}: \033[1;32m{entry['command']}\033[0m (Task: {entry['input']})")
        return

    if args.reuse:
        command, user_input = get_history_command(args.reuse)
        if command:
            print("\033[1;34mReusing Command:\033[0m")
            print(f"\033[1;32m{command}\033[0m")
            print("\033[1;34m-" * 40 + "\033[0m")
            success, error = run_command_normal(command, args.verbose)
            if success:
                print("\033[1;32mSuccess\033[0m")
                show_changes()
            else:
                print(f"\033[1;31m{error}\033[0m")
        else:
            print("\033[1;31mInvalid history index.\033[0m")
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
        print("\033[1;34mCommand:\033[0m")
        print(f"\033[1;32m{command}\033[0m")
        if args.verbose and explanation:
            print("\033[1;34mExplanation:\033[0m")
            print(f"\033[1;36m{explanation}\033[0m")
        print("\033[1;34m-" * 40 + "\033[0m")

        if "Error" in command:
            print(f"\033[1;31m{command}\033[0m")
            return

        save_history(user_input, command)
        success, error = run_command_normal(command, args.verbose)
        if success:
            print("\033[1;32mSuccess\033[0m")
            show_changes()
        else:
            print(f"\033[1;31m{error}\033[0m")
            if args.verbose:
                explanation = get_error_explanation(error)
                print("\033[1;34mError Explanation:\033[0m")
                print(f"\033[1;36m{explanation}\033[0m")
            print("\033[1;34mGenerating alternative...\033[0m")
            new_command, new_explanation = generate_command(user_input, error, args.verbose)
            print("\033[1;34mNew Command:\033[0m")
            print(f"\033[1;32m{new_command}\033[0m")
            if args.verbose and new_explanation:
                print("\033[1;34mExplanation:\033[0m")
                print(f"\033[1;36m{new_explanation}\033[0m")
            print("\033[1;34m-" * 40 + "\033[0m")
            if "Error" in new_command:
                print(f"\033[1;31m{new_command}\033[0m")
                return
            save_history(user_input, new_command)
            success, error = run_command_normal(new_command, args.verbose)
            if success:
                print("\033[1;32mSuccess\033[0m")
                show_changes()
            else:
                print(f"\033[1;31m{error}\033[0m")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
LinAIx Natural Language Terminal: AI-powered shell
Type what you want to do in plain English. No shell commands allowed!
All actions are interpreted and executed by AI.
"""
import sys
import os
import re
import json
import time
import subprocess
from pathlib import Path
import argparse
import google.generativeai as genai
import shutil

ANSI_GREEN = "\033[1;32m"
ANSI_RED = "\033[1;31m"
ANSI_YELLOW = "\033[1;33m"
ANSI_BLUE = "\033[1;34m"
ANSI_CYAN = "\033[1;36m"
ANSI_MAGENTA = "\033[1;35m"
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"

CONFIG_DIR = Path.home() / ".linaix"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_CONFIG_FILE = Path(__file__).parent / "default_linaix_config.json"

def load_default_config():
    try:
        with DEFAULT_CONFIG_FILE.open("r") as f:
            return json.load(f)
    except Exception as e:
        print(f"{ANSI_RED}Error loading default config: {str(e)}{ANSI_RESET}")
        return {
            "api_key": "",
            "model": "gemini-1.5-flash",
            "auto_run_safe": False,
            "aliases": {}
        }

def load_config():
    default_config = load_default_config()
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir()
    if not CONFIG_FILE.exists() or CONFIG_FILE.stat().st_size == 0:
        with CONFIG_FILE.open("w") as f:
            json.dump(default_config, f, indent=2)
    try:
        with CONFIG_FILE.open("r") as f:
            config = json.load(f)
    except json.JSONDecodeError:
        with CONFIG_FILE.open("w") as f:
            json.dump(default_config, f, indent=2)
        config = default_config.copy()
    if not config["api_key"] and "GOOGLE_API_KEY" in os.environ:
        config["api_key"] = os.environ["GOOGLE_API_KEY"]
    if not config["api_key"]:
        print(f"{ANSI_RED}Error: No Google API key found. Set it in {CONFIG_FILE} or export GOOGLE_API_KEY.{ANSI_RESET}")
        sys.exit(1)
    return config

config = load_config()
genai.configure(api_key=config["api_key"])

def generate_command(user_input, error_context=None, verbose=False):
    try:
        model = genai.GenerativeModel(config["model"])
        current_dir = os.getcwd()
        prompt = f"Generate a single, safe, correct Linux command for a Debian-based system to: {user_input}. Current directory: {current_dir}. Return only the command."
        if error_context:
            prompt += f" Previous command failed with error: '{error_context}'. Suggest a corrected command."
        if verbose:
            prompt += " Additionally, return a brief explanation in the format: [EXPLANATION: ...]"
        response = model.generate_content(prompt)
        text = response.text.strip()
        command = re.sub(r'```bash\n|```|\n\[EXPLANATION:.*', '', text).strip()
        explanation = re.search(r'\[EXPLANATION: (.*?)\]', text)
        explanation = explanation.group(1) if explanation else ""
        return command if command else None, explanation
    except Exception as e:
        print(f"{ANSI_RED}Error: Could not generate command: {str(e)}{ANSI_RESET}")
        return None, ""

def run_command(command):
    if command.strip().startswith("cd "):
        try:
            new_dir = command.strip().split(" ", 1)[1]
            os.chdir(os.path.expanduser(new_dir))
            print(f"{ANSI_GREEN}Changed directory to: {os.getcwd()}{ANSI_RESET}")
            return True, ""
        except Exception as e:
            return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"
    try:
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        if result.stdout:
            print(f"{ANSI_CYAN}Output:{ANSI_RESET}\n{result.stdout.strip()}")
        if result.stderr:
            print(f"{ANSI_RED}Error:{ANSI_RESET}\n{result.stderr.strip()}")
        return result.returncode == 0, result.stderr.strip()
    except Exception as e:
        return False, f"{ANSI_RED}Error: {str(e)}{ANSI_RESET}"

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
            success, error = run_command(command)
            if success:
                print(f"{ANSI_GREEN}✓ Success{ANSI_RESET}")
            else:
                print(f"{ANSI_RED}✗ Error: {error}{ANSI_RESET}")
        except (EOFError, KeyboardInterrupt):
            print(f"\n{ANSI_GREEN}Goodbye!{ANSI_RESET}")
            break

def parse_args():
    parser = argparse.ArgumentParser(description="LinAIx Natural Language Terminal")
    parser.add_argument("--verbose", action="store_true", help="Show explanations for generated commands")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    nl_terminal(verbose=args.verbose) 
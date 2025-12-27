#!/usr/bin/env python3

import argparse
import json
import logging
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
import platform
from typing import Any, Dict, List, Tuple

from .providers import (
    generate_with_google,
    generate_with_openai,
    normalize_provider_name,
    ProviderError,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".linaix"
CONFIG_FILE = CONFIG_DIR / "config.json"

ANSI_GREEN = "\033[1;32m"
ANSI_RED = "\033[1;31m"
ANSI_YELLOW = "\033[1;33m"
ANSI_BLUE = "\033[1;34m"
ANSI_CYAN = "\033[1;36m"
ANSI_RESET = "\033[0m"

MAX_INPUT_LENGTH = 800
MAX_COMMAND_LENGTH = 400
COMMAND_TIMEOUT = 30

DEFAULT_CONFIG: Dict[str, Any] = {
    "provider": "google",
    "google_api_key": "",
    "openai_api_key": "",
}

BLOCKED_BASE_COMMANDS = {
    "rm",
    "dd",
    "mkfs",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "chmod",
    "chown",
    "kill",
    "killall",
    "pkill",
    "iptables",
    "ufw",
    "firewall-cmd",
    "systemctl",
    "service",
    "sudo",
    "su",
    "doas",
    "pkexec",
}

SUSPICIOUS_PATTERNS = [
    re.compile(r"rm\s+-rf\s+/"),
    re.compile(r":\(\)\s*\{.*:\|.*:&.*\};:"),
    re.compile(r">\s*/dev/null"),
    re.compile(r"/dev/sd[a-z]"),
]


class ValidationError(Exception):
    """Raised when user input or model output is invalid."""


class CommandSafetyError(Exception):
    """Raised when a generated command is unsafe to run automatically."""


def load_config() -> Dict[str, Any]:
    """Load config, creating defaults if needed."""
    try:
        if not CONFIG_DIR.exists():
            CONFIG_DIR.mkdir(mode=0o700)

        if not CONFIG_FILE.exists() or CONFIG_FILE.stat().st_size == 0:
            with CONFIG_FILE.open("w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            os.chmod(CONFIG_FILE, 0o600)

        with CONFIG_FILE.open("r") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValidationError("Config file is not a JSON object")

        for key, default_value in DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = default_value

        # Populate API keys from environment, if present
        # Prefer GOOGLE_API_KEY, but accept GEMINI_API_KEY as well
        if not data.get("google_api_key") and ("GOOGLE_API_KEY" in os.environ or "GEMINI_API_KEY" in os.environ):
            data["google_api_key"] = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
        if not data.get("openai_api_key") and ("OPENAI_API_KEY" in os.environ or "OPENAI_APIKEY" in os.environ):
            data["openai_api_key"] = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_APIKEY") or ""

        return data
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"{ANSI_RED}Error loading config: {exc}{ANSI_RESET}")
        sys.exit(1)


def save_config(config: Dict[str, Any]) -> None:
    try:
        if not CONFIG_DIR.exists():
            CONFIG_DIR.mkdir(mode=0o700)
        with CONFIG_FILE.open("w") as f:
            json.dump(config, f, indent=2)
        os.chmod(CONFIG_FILE, 0o600)
    except OSError as exc:
        print(f"{ANSI_RED}Error saving config: {exc}{ANSI_RESET}")


def validate_input(user_input: str) -> str:
    if not isinstance(user_input, str) or not user_input.strip():
        raise ValidationError("Task must be a non-empty string")
    if len(user_input) > MAX_INPUT_LENGTH:
        raise ValidationError(f"Task is too long (max {MAX_INPUT_LENGTH} characters)")
    if re.search(r"[;&|`$><]", user_input):
        raise ValidationError("Task must not contain shell control characters (;, |, &, <, >, `, $)")
    return user_input.strip()


def validate_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise ValidationError("Generated command is empty")
    if len(command) > MAX_COMMAND_LENGTH:
        raise ValidationError(f"Generated command too long (max {MAX_COMMAND_LENGTH} characters)")
    if re.search(r"[;&|`$]", command):
        raise CommandSafetyError("Generated command contains chained or subshell operators; single commands only")
    return command.strip()


def parse_command(command: str) -> Tuple[str, List[str]]:
    command = validate_command(command)
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise ValidationError(f"Cannot parse generated command: {exc}")
    if not parts:
        raise ValidationError("Generated command is empty after parsing")
    return parts[0].lower(), parts


def is_blocked(base_command: str) -> bool:
    return base_command in BLOCKED_BASE_COMMANDS


def looks_destructive(command: str) -> bool:
    lowered = command.lower()
    if any(pattern.search(lowered) for pattern in SUSPICIOUS_PATTERNS):
        return True
    return False


def clean_model_output(text: str) -> str:
    """Strip code fences and keep the first non-empty line."""
    cleaned = re.sub(r"```(?:bash)?\s*([\s\S]*?)```", r"\1", text, flags=re.MULTILINE).strip()
    for line in cleaned.splitlines():
        if line.strip():
            return line.strip()
    return cleaned


def os_shell_defaults() -> Tuple[str, str]:
    sysname = platform.system()
    if sysname == "Windows":
        return sysname, "powershell"
    if sysname == "Darwin":
        return sysname, "zsh"
    return sysname, "bash"


def detect_current_shell() -> str:
    sysname = platform.system()
    if sysname == "Windows":
        # Detect PowerShell via environment variables typically present in PS sessions
        if os.environ.get("PSModulePath") or os.environ.get("PowerShellEdition"):
            return "powershell"
        comspec = (os.environ.get("ComSpec", "").lower())
        if "cmd.exe" in comspec:
            return "cmd"
        return "powershell"
    # POSIX/macOS: use SHELL
    shell_path = os.environ.get("SHELL", "")
    base = os.path.basename(shell_path).lower()
    if base in {"zsh", "bash"}:
        return base
    if base in {"fish", "sh"}:
        return "bash"
    # Default per-OS
    return os_shell_defaults()[1]


def build_prompt(task: str, shell: str, sysname: str) -> str:
    base = (
        "You are an assistant that writes exactly one command for the user's system. "
        "Return only the command line; no explanations or code fences. "
        "The command must be safe, single-step, and not use pipes, redirection, or subshells. "
    )
    os_note = f"Target OS: {sysname}. Preferred shell: {shell}. "
    cwd_note = "Assume current working directory is the user's cwd. "
    task_note = f"Task: {task}"
    return base + os_note + cwd_note + task_note


def generate_command(task: str, provider: str, model_name: str, shell: str, sysname: str) -> str:
    prompt = build_prompt(task, shell, sysname)
    provider_norm = normalize_provider_name(provider)
    try:
        if provider_norm == "google":
            text = generate_with_google(load_config()["google_api_key"], model_name, prompt)
        else:
            text = generate_with_openai(load_config()["openai_api_key"], model_name, prompt)
        return clean_model_output(text)
    except ProviderError as exc:
        raise ValidationError(str(exc))


def execute_command(command_parts: List[str], timeout: int) -> Tuple[int, str, str]:
    try:
        result = subprocess.run(
            command_parts,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        return result.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout} seconds"
    except OSError as exc:
        return 126, "", f"OS error: {exc}"


def execute_in_shell(command: str, shell: str, timeout: int) -> Tuple[int, str, str]:
    try:
        if shell == "powershell":
            cmd = ["powershell", "-NoProfile", "-Command", command]
        elif shell == "cmd":
            cmd = ["cmd.exe", "/C", command]
        elif shell == "zsh":
            cmd = ["/bin/zsh", "-lc", command]
        else:  # bash default
            cmd = ["/bin/bash", "-lc", command]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        return result.returncode, stdout, stderr
    except FileNotFoundError:
        return 127, "", f"Shell '{shell}' not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout} seconds"
    except OSError as exc:
        return 126, "", f"OS error: {exc}"


def confirm(prompt: str) -> bool:
    answer = input(prompt).strip().lower()
    return answer in {"y", "yes"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and optionally run a single shell command from natural language")
    parser.add_argument("task", nargs="*", help="What you want to do")
    parser.add_argument("--provider", choices=["google", "openai"], default=None, help="LLM provider to use (default from config)")
    parser.add_argument("--model", required=False, help="Model name for the selected provider (required)")
    parser.add_argument("--yes", action="store_true", help="Run without confirmation")
    parser.add_argument("--dry-run", action="store_true", help="Only show the generated command")
    parser.add_argument("--timeout", type=int, default=COMMAND_TIMEOUT, help="Command timeout in seconds")
    parser.add_argument("--shell", choices=["auto", "bash", "zsh", "powershell", "cmd"], default="auto", help="Shell to execute in (auto-detect by OS)")
    parser.add_argument("--set-api-key", help="Store the provided API key for the current provider and exit")
    parser.add_argument("--set-google-key", help="Store Google (Gemini) API key and exit")
    parser.add_argument("--set-openai-key", help="Store OpenAI API key and exit")

    args = parser.parse_args()

    if args.set_google_key or args.set_openai_key or args.set_api_key:
        config = load_config()
        if args.set_google_key:
            config["google_api_key"] = args.set_google_key.strip()
            config["provider"] = "google"
            print(f"{ANSI_GREEN}Google API key saved.{ANSI_RESET}")
        if args.set_openai_key:
            config["openai_api_key"] = args.set_openai_key.strip()
            config["provider"] = "openai"
            print(f"{ANSI_GREEN}OpenAI API key saved.{ANSI_RESET}")
        if args.set_api_key:
            prov = normalize_provider_name(args.provider or load_config().get("provider", "google"))
            key_field = "google_api_key" if prov == "google" else "openai_api_key"
            config[key_field] = args.set_api_key.strip()
            config["provider"] = prov
            print(f"{ANSI_GREEN}API key saved for provider '{prov}'.{ANSI_RESET}")
        save_config(config)
        print(f"{ANSI_GREEN}Config written to {CONFIG_FILE}{ANSI_RESET}")
        return

    task_text = " ".join(args.task).strip()
    if not task_text:
        parser.print_help()
        sys.exit(1)

    try:
        validated_task = validate_input(task_text)
    except ValidationError as exc:
        print(f"{ANSI_RED}Invalid task: {exc}{ANSI_RESET}")
        sys.exit(1)

    config = load_config()
    # Provider selection
    provider = normalize_provider_name(args.provider or config.get("provider", "google"))
    # Require an explicit model selection by the user
    if not args.model:
        model_hint = "e.g., gemini-1.5-pro" if provider == "google" else "e.g., gpt-4o-mini"
        print(f"{ANSI_RED}No model specified for provider '{provider}'. Use --model <name> ({model_hint}).{ANSI_RESET}")
        sys.exit(1)

    # Resolve shell
    sysname, default_shell = os_shell_defaults()
    shell = detect_current_shell() if args.shell == "auto" else args.shell

    # Verify API key availability
    key_ok = (config.get("google_api_key") if provider == "google" else config.get("openai_api_key"))
    if not key_ok:
        need = "GOOGLE_API_KEY" if provider == "google" else "OPENAI_API_KEY"
        print(f"{ANSI_RED}No API key set for {provider}. Use --set-{provider}-key or set {need}.{ANSI_RESET}")
        sys.exit(1)

    try:
        model_name = args.model
        command = generate_command(validated_task, provider, model_name, shell, sysname)
        base, parts = parse_command(command)
    except (ValidationError, CommandSafetyError) as exc:
        print(f"{ANSI_RED}Could not generate a safe command: {exc}{ANSI_RESET}")
        sys.exit(1)
    except Exception as exc:
        print(f"{ANSI_RED}Command generation failed: {exc}{ANSI_RESET}")
        sys.exit(1)

    print(f"{ANSI_BLUE}Generated:{ANSI_RESET} {ANSI_GREEN}{command}{ANSI_RESET}")

    if args.dry_run:
        return

    if is_blocked(base):
        print(f"{ANSI_RED}Blocked command '{base}' will not be executed.{ANSI_RESET}")
        sys.exit(1)

    if looks_destructive(command):
        print(f"{ANSI_YELLOW}Command looks destructive; run at your own risk.{ANSI_RESET}")

    if not args.yes:
        if not confirm(f"{ANSI_YELLOW}Run this command? [y/N]: {ANSI_RESET}"):
            print(f"{ANSI_YELLOW}Not executed.{ANSI_RESET}")
            return

    if shell in {"bash", "zsh", "powershell", "cmd"}:
        code, stdout, stderr = execute_in_shell(command, shell, args.timeout)
    else:
        code, stdout, stderr = execute_command(parts, args.timeout)

    if stdout:
        print(f"{ANSI_CYAN}Output:{ANSI_RESET}\n{stdout}")
    if stderr:
        print(f"{ANSI_RED}Error:{ANSI_RESET}\n{stderr}")

    sys.exit(code)


if __name__ == "__main__":
    main()
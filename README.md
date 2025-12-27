<div align="center">

# LinAIx
# LinAIx

Simple, safe, cross-platform command generation. Describe what you want; LinAIx outputs one OS-appropriate shell command and can run it after confirmation.

## Install

```bash
pip install linaix
# or from source
pip install -e .
```

## Setup

Choose a provider and set an API key:

```bash
# Google (Gemini)
linaix --set-google-key YOUR_GOOGLE_API_KEY
# OpenAI (ChatGPT)
linaix --set-openai-key YOUR_OPENAI_API_KEY

# Optional: environment variables
export GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY
export GEMINI_API_KEY=YOUR_GOOGLE_API_KEY
export OPENAI_API_KEY=YOUR_OPENAI_API_KEY
```

## Use

```bash
# Generate and run (with confirmation)
linaix "list all python files"

# Preview only
linaix --dry-run "create a directory named backup"

# Skip confirmation
linaix --yes "show disk usage"

# Pick provider/model (model is required)
linaix --provider google --model gemini-1.5-pro "task"
linaix --provider openai --model gpt-4o-mini "task"

# Choose shell (auto = detect current shell)
linaix --shell auto "task"
linaix --shell bash "task"
linaix --shell zsh "task"
linaix --shell powershell "task"
linaix --shell cmd "task"

# Timeout (seconds)
linaix --timeout 60 "task"
```

## Safety

- Single command only; no pipes, redirects, or subshells
- Confirmation before execution (use `--yes` to skip)
- Blocks dangerous commands (rm, dd, chown, shutdown, etc.)
- Warns on suspicious patterns (e.g., `rm -rf /`)

## Config

Config is stored at `~/.linaix/config.json`:

```json
{
  "provider": "google",
  "google_api_key": "",
  "openai_api_key": "",
}
```

## Troubleshooting

- "No API key" → set with `--set-google-key` or `--set-openai-key`, or export `GOOGLE_API_KEY` / `OPENAI_API_KEY`.
- "Permission denied" → reinstall `pip install --force-reinstall linaix` or check PATH.

## License

MIT
cd linaix
pip install -e .
```

**Note**: For development and contributing, you can install from source using the above commands. For regular usage, use `pip install linaix`.

### **Code Style**
- Follow PEP 8 guidelines
- Add type hints where appropriate
- Include docstrings for new functions
- Write tests for new features

---

##  License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


<div align="center">


[![GitHub stars](https://img.shields.io/github/stars/AdirAli/linaix?style=social)](https://github.com/AdirAli/linaix)
[![GitHub forks](https://img.shields.io/github/forks/AdirAli/linaix?style=social)](https://github.com/AdirAli/linaix)
[![GitHub issues](https://img.shields.io/github/issues/AdirAli/linaix)](https://github.com/AdirAli/linaix/issues)

</div>

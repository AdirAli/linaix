# LinAIx - Open Source command line AI Assistant

 ![Uploading image.png…]()


> **AI-powered Linux Command Assistant**

LinAIx is a command-line tool that lets you control your Linux system using natural language. Powered by Google Gemini, it generates safe, context-aware Linux commands from your plain English requests.



---

## ✨ Features

- **Natural Language Terminal**: Open a real terminal window and type what you want to do—no shell commands needed!
- **AI Command Generation**: Converts your tasks ("list all python files", "make a backup of my documents") into safe, correct Linux commands.
- **Command History**: Keeps a record of your tasks and generated commands for easy reuse.
- **Aliases**: Create shortcuts for common tasks (e.g., `listpy` for "list all python files").
- **Destructive Command Safety**: Warns you before running dangerous commands like `rm`.
- **Google Gemini Integration**: Uses the Gemini API for smart, context-aware command generation.
- **Configurable**: All settings are managed in a simple JSON config file.

---

## 🚀 Quick Start

### 1. **Install Requirements**
```bash
pip install -r requirements.txt
```

### 2. **Get a Google API Key**
- Sign up at [Google AI Studio](https://aistudio.google.com/app/apikey)
- Copy your API key

### 3. **Configure LinAIx**
- On first run, LinAIx will create a config file at `~/.linaix/config.json`.
- Or, set your API key with:
  ```bash
  python linaix.py --set-api-key 'your-api-key-here'
  ```
- Or, export it as an environment variable:
  ```bash
  export GOOGLE_API_KEY='your-api-key-here'
  ```

---

## 🖥️ Usage

### **Natural Language Interactive Mode** (Linux only)
Open a new AI-powered terminal:
```bash
python linaix.py --interactive
```
- A new GNOME Terminal window will open.
- Type your tasks in plain English (e.g., `find all .txt files and zip them`).
- The AI will generate and run the right command for you.
- Type `exit` to quit.

### **One-off Command Generation**
Generate and (optionally) run a command for a single task:
```bash
python linaix.py 'list all python files'
```
- Add `--verbose` to see an explanation:
  ```bash
  python linaix.py --verbose 'create a directory'
  ```

### **Aliases**
- Add an alias:
  ```bash
  python linaix.py --add-alias listpy 'list all python files'
  ```
- Use an alias:
  ```bash
  python linaix.py listpy
  ```
- List aliases:
  ```bash
  python linaix.py --list-aliases
  ```
- Remove an alias:
  ```bash
  python linaix.py --remove-alias listpy
  ```

### **Command History**
- Show history:
  ```bash
  python linaix.py --history
  ```
- Reuse a command from history:
  ```bash
  python linaix.py --reuse 2
  ```

---

## ⚠️ Notes
- **Linux only:** The interactive mode requires GNOME Terminal and is not supported on Windows or macOS.
- **No raw shell commands in interactive mode:** Only natural language tasks are accepted.
- **API key required:** You must provide a valid Google API key.

---

## 🛠️ Configuration
- Default config is stored in `default_linaix_config.json` (in the repo).
- User config is at `~/.linaix/config.json`.
- You can edit the config file directly to change settings (model, aliases, etc).

---

## 📄 License
MIT

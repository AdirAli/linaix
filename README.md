# LinAIx: Linux Command Assistant

LinAIx is an open-source Linux command-line assistant powered by the Google Gemini API. It helps users generate and execute Linux commands interactively or via specific tasks, running directly in the current terminal. Great way to learn linux command through hand on experience.

## Features
- Generate Linux commands for tasks (e.g., "create a new file").
- Interactive mode with command history and aliases.
- Safe execution with confirmation for destructive commands.
- Support for custom aliases and verbose explanations.

## Installation

### Prerequisites
- Python 3.6 or higher
- pip (Python package manager)

### Steps
1. **Clone the Repository++
   ```bash
   git clone https://github.com/AdirAli/linaix.git
   cd linaix
   ```

2. **Install Dependencies**
   ```bash
   sudo pip3 install google-generativeai prompt_toolkit
   ```

3. **Obtain a Google API Key**
   - Go to [Google AI Studio](https://aistudio.google.com/app/apikey) and create an API key.
   - Set the API key in one of two ways:
     - Edit `~/.linaix/config.json` and add your key:
       ```json
       {
         "api_key": "your-google-api-key",
         "model": "gemini-1.5-flash",
         "auto_run_safe": false,
         "aliases": {}
       }
       ```
     - Or export it as an environment variable:
       ```bash
       export GOOGLE_API_KEY="your-google-api-key"
       ```

4. **Make the Script Executable**
   ```bash
   chmod +x linaix.py
   ```

5. **Run the Script**
   - Locally:
     ```bash
     ./linaix.py --interactive
     ```
   - Or move to a global path (optional):
     ```bash
     sudo cp linaix.py /usr/local/bin/linaix
     sudo chmod +x /usr/local/bin/linaix
     linaix --interactive
     ```

## Usage
- Run `linaix --help` for available options.
- Example: `linaix 'list all python files'` generates and executes `ls *.py` in the current terminal.
- Interactive mode: Enter tasks or commands directly (e.g., `make a new file test.txt`).

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute. We welcome enhancements like terminal control, error logging, or additional AI models.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments
- Powered by the Google Gemini API.
- Built to expand my knowledge curve and contrinute to the open source community

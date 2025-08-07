# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.1.2] - Update - 2025-08-07

### Fixed
- **API Key UX Bug**: Fixed issue where `--help` and `--setup` commands required API key
- **Improved Setup Experience**: Users can now access setup instructions without pre-configured API key

### Added
- **Linux Distribution Support**: Automatic detection of Linux distribution
- **Distribution-Aware Command Generation**: AI prompts now include detected distribution information

### Supported Distributions
- Ubuntu
- Debian
- Fedora
- Arch Linux
- CentOS
- Red Hat Enterprise Linux
- openSUSE
- Linux Mint

### Technical Changes
- Updated prompt templates to be distribution-aware
- Enhanced error handling for distribution detection
- Refactored configuration management for better UX


## [0.1.1] - Update - 2025-08-06

### Added
- **Linux Distribution Support**: Automatic detection of Linux distribution
- **Distribution-Aware Command Generation**: AI prompts now include detected distribution information

### Supported Distributions
- Ubuntu
- Debian
- Fedora
- Arch Linux
- CentOS
- Red Hat Enterprise Linux
- openSUSE
- Linux Mint

### Technical Changes
- Updated prompt templates to be distribution-aware
- Enhanced error handling for distribution detection


## [0.1.0] - Initial Development

### Added
- Core LinAIx functionality
- Google Gemini AI integration
- Command-line interface
-Basic natural language command generation
 Interactive terminal mode
- Command history and aliases
- Configuration management

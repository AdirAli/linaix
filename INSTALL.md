# Installing Linaix

## From Source (Development Installation)

1. Clone the repository:
```bash
git clone https://github.com/yourusername/linaix.git
cd linaix
```

2. Install in development mode:
```bash
pip install -e .
```

## Building and Installing the Package

1. Build the package:
```bash
python -m build
```

2. Install the built package:
```bash
pip install dist/linaix-0.1.0.tar.gz
```

## Using Linaix

After installation, you can run linaix using:
```bash
linaix
```

Or from Python:
```python
from linaix import main
main()
```

## Publishing to PyPI (Optional)

If you want to publish your package to PyPI:

1. Install build tools:
```bash
pip install build twine
```

2. Build the package:
```bash
python -m build
```

3. Upload to PyPI (you'll need a PyPI account):
```bash
twine upload dist/*
```

## Development

For development, install with dev dependencies:
```bash
pip install -e .[dev]
``` 
# Publishing Linaix to PyPI

This guide will help you publish your `linaix` package to PyPI so users can install it with `pip install linaix`.

## Prerequisites

1. **PyPI Account**: Create an account at [PyPI](https://pypi.org/account/register/)
2. **TestPyPI Account**: Create an account at [TestPyPI](https://test.pypi.org/account/register/) (for testing)

## Step 1: Install Publishing Tools

```bash
pip install build twine
```

## Step 2: Build Your Package

```bash
python -m build
```

This creates two files in the `dist/` directory:
- `linaix-0.1.0.tar.gz` (source distribution)
- `linaix-0.1.0-py3-none-any.whl` (wheel distribution)

## Step 3: Test on TestPyPI (Recommended)

First, test your package on TestPyPI:

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ linaix
```

## Step 4: Publish to PyPI

If everything works on TestPyPI, publish to the real PyPI:

```bash
twine upload dist/*
```

## Step 5: Verify Installation

After publishing, users can install your package with:

```bash
pip install linaix
```

And run it with:
```bash
linaix --help
```

## Updating Your Package

When you make changes:

1. Update the version in `pyproject.toml` and `setup.py`
2. Build the new version: `python -m build`
3. Upload to PyPI: `twine upload dist/*`

## Important Notes

- **Package Name**: Make sure the name "linaix" is available on PyPI. If not, you'll need to choose a different name.
- **Version Numbers**: Each upload must have a unique version number.
- **API Keys**: Users will still need to set up their Google API key after installation.
- **Documentation**: Consider adding more documentation to your README.md for PyPI users.

## Troubleshooting

### Package Name Already Taken
If "linaix" is already taken, you can:
- Use a different name (e.g., "linaix-cli", "linaix-terminal")
- Contact the owner of the existing package
- Use a different namespace

### Upload Errors
- Make sure you're logged in: `twine check dist/*`
- Verify your credentials are correct
- Check that the package name is available

### Installation Issues
- Test locally first: `pip install -e .`
- Check that all dependencies are correctly listed
- Verify the entry point is working: `linaix --help` 
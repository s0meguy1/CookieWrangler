# CookieWrangler

A Python command-line tool that exports and imports cookies and local storage from Chrome/Firefox. Supports full export/import functionality for both browsers on Windows, with partial Linux support via the `--linux` flag.

## Features

- **Export cookies** from Chrome or Firefox into JSON
- **Export local storage** from Chrome or Firefox
- **Import cookies** into a Firefox profile from a JSON file
- **Import local storage** into a Firefox profile
- **Combined import** of cookies and local storage from a single JSON file

## Requirements

- **Python 3.6+** recommended
- For **Chrome**:
  - `requests` and `websocket-client` for cookie access
  - `plyvel` for local storage access (requires LevelDB)
- For Firefox, no extra dependencies required (uses built-in `sqlite3`)

### Installing plyvel (for Chrome local storage)

Chrome local storage requires `plyvel`, which needs LevelDB. Here's how to set it up on Windows:

1. **Install vcpkg and LevelDB**:
```bash
git clone https://github.com/microsoft/vcpkg.git
cd vcpkg
bootstrap-vcpkg.bat

# Set environment variables
$env:VCPKG_ROOT = "C:\path\to\vcpkg"
$env:PATH = "$env:VCPKG_ROOT;$env:PATH"

# Install LevelDB
vcpkg install leveldb

# Set include and lib paths
$env:INCLUDE = "C:\Users\[USER]\Documents\vcpkg\installed\x64-windows\include"
$env:LIB = "C:\Users\[USER]\Documents\vcpkg\installed\x64-windows\lib"
```

2. **Install plyvel**:
```bash
python -m pip install plyvel
```

## Quick Start

1. **Install dependencies**:
```bash
pip install requests websocket-client plyvel
```

2. **Basic usage**:

Export Chrome data:
```bash
python script.py --chrome --output exported.json --local-storage
```

Export Firefox data:
```bash
python script.py --firefox --output exported.json --local-storage
```

## Detailed Usage

### Export Chrome Data
```bash
# Export both cookies and local storage
python script.py --chrome --output chrome_exported.json --local-storage

# Export only cookies
python script.py --chrome --output chrome_exported.json
```

### Export Firefox Data
```bash
# Export both cookies and local storage
python script.py --firefox --output firefox_exported.json --local-storage

# Export with specific profile directory
python script.py --firefox --output exported.json --local-storage \
 --profile-dir "C:\Users\[USER]\AppData\Roaming\Mozilla\Firefox\Profiles\[PROFILE-NAME].default-release"
```

### Import Data to Firefox
```bash
# Import both cookies and local storage
python script.py --import-all imported.json

# Import with specific profile
python script.py --import-all imported.json \
 --profile-dir "C:\Users\[USER]\AppData\Roaming\Mozilla\Firefox\Profiles\[PROFILE-NAME].default-release"
```

### Additional Options

- `--db PATH` - Specify cookie database location
- `--default-host HOSTNAME` - Set default host for hostless cookies
- `--linux` - Use Linux-style Firefox paths
- `--profile-dir PATH` - Specify Firefox profile directory

## JSON Format

The tool uses this JSON structure for import/export:

```json
{
  "cookies": [
    {
      "name": "cookie_name",
      "value": "cookie_value",
      "host": "example.com",
      "path": "/",
      "expiry": 1234567890,
      "isSecure": true,
      "isHttpOnly": false
    }
  ],
  "local_storage": {
    "https://example.com": {
      "key1": "value1",
      "key2": "value2"
    },
    "chrome://settings": {
      "setting1": "value1"
    }
  }
}
```

## Important Notes

- **Always backup** your browser profiles before importing data
- Chrome local storage requires proper LevelDB/plyvel setup
- Cookie manipulation has security implications - use responsibly
- Some features may be Windows-specific

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

MIT License - see LICENSE file for details.

---

Found this useful? Give us a ⭐ on GitHub!

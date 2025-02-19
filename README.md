# CookieWrangler

A Python command-line tool that exports and imports cookies (and local storage) from Chrome/Firefox. Includes support for exporting/importing Firefox local storage as well. Designed for Windows paths, but partially adaptable to Linux with the `--linux` flag.

## Features

- **Export cookies** from Chrome or Firefox into JSON
- **Import cookies** into a Firefox profile from a JSON file
- **Export local storage** from a Firefox profile
- **Import local storage** into a Firefox profile
- **Combined import** of cookies and local storage from a single JSON file

## Requirements

- **Python 3.6+** recommended
- For **Chrome cookie decryption** on Windows:
  - `pywin32` (`pip install pywin32`)
  - `pycryptodomex` (`pip install pycryptodomex`)
- For Firefox, no extra pip dependencies are strictly required for basic SQLite access (uses built-in `sqlite3`), but the script depends on standard Python modules and `glob`.

> **Note**: Some paths and features are Windows-specific; local storage for Chrome is not yet fully implemented.

## Installation

1. **Clone** this repository or **download** the script:

   ```bash
   git clone https://github.com/YourUsername/CookieWrangler.git
   cd CookieWrangler
   ```

2. (Optional) **Install** Python dependencies if you intend to work with Chrome cookies on Windows:

   ```bash
   pip install pywin32 pycryptodomex
   ```

3. Make sure you have the necessary **read/write permissions** if you’re working with browser profile directories.

## Usage

Run the script with `python script.py [options]`. Below are some common use cases.

### 1. Export Firefox Cookies

```bash
python script.py --firefox --output exported.json
```

By default, it attempts to find a Firefox profile in the standard user profile directory.

### 2. Export Firefox Cookies **and** Local Storage

```bash
python script.py --firefox --output exported.json --local-storage
```

### 3. Specify a Particular Firefox Profile

```bash
python script.py --firefox --output exported.json --local-storage \
 --profile-dir "C:\Users\[USER]\AppData\Roaming\Mozilla\Firefox\Profiles\[PROFILE-NAME].default-release"
```

### 4. Import All (Cookies + Local Storage) from a Single JSON File

```bash
python script.py --import-all imported.json
```

Optionally specifying a Firefox profile:

```bash
python script.py --import-all imported.json --profile-dir "C:\Users\[USER]\AppData\Roaming\Mozilla\Firefox\Profiles\[PROFILE-NAME].default-release"
```

### 5. Export Chrome Cookies (Experimental)

```bash
python script.py --chrome --output chrome_exported.json
```
> **Note**: Chrome export requires `pywin32` and `pycryptodomex` installed. Currently, only tested on Windows.

### Additional Options

- `--db PATH`  
  Use a specific cookie database file instead of auto-detecting.  
- `--default-host HOSTNAME`  
  Specify a default host for cookies that have no host set.  
- `--linux`  
  Tweak the internal logic to look for Linux-style Firefox profiles (e.g. `~/.mozilla/firefox`).

For **more advanced usage** details, see the `main()` function’s help text in `script.py` or run:

```bash
python script.py --help
```

## JSON Structure for Imports

When you **import** cookies or local storage from JSON, the file should follow this structure:

```json
{
  "cookies": [
    {
      "name": "...",
      "value": "...",
      "host": "...",
      "path": "...",
      "expiry": "...",
      ...
    }
  ],
  "local_storage": {
    "https://example.com": {
      "myKey": "myValue",
      "anotherKey": "anotherValue"
    },
    "http://anotherdomain.com": {
      "someKey": "someValue"
    }
  }
}
```

- `cookies` is a **list** of cookie objects.  
- `local_storage` is a **dictionary** with origins (e.g., `"https://example.com"`) as keys, and a dictionary of key/value pairs as values.

## Important Notes and Disclaimer

- This script can **read** from and **write** to browser databases. **Always back up** important profiles or data before running import operations.
- Local storage for **Chrome** is currently **not fully implemented**—Firefox local storage is the primary focus.
- Keep in mind some **encryption and platform-specific** complexities, especially for Chrome cookies on non-Windows platforms.
- Use responsibly: manipulating or sharing cookies can have **security and privacy** implications.

## Contributing

Contributions or testing across different OSes and browsers are welcome! Feel free to:

1. **Fork** the repo
2. Create a **branch** for your feature or fix
3. Submit a **pull request**

## License

This project is licensed under the [MIT License](LICENSE).

---

Have fun wrangling your cookies! 

*Enjoy **CookieWrangler**? Give us a ⭐ on GitHub!*

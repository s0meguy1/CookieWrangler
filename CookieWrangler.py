#!/usr/bin/env python

import argparse
from urllib.parse import urlparse  # For URL parsing in local storage handling
import sqlite3
import json
import datetime
import time
import os
from os.path import expandvars, dirname, join, exists
from glob import glob
import sys
from pathlib import Path
import requests
import websocket # pip install requests websocket-client
import subprocess

# ----- Chrome Cookies Functionality -----
def get_chrome_cookies():
    """Retrieve Chrome cookies via DevTools Protocol (Verified Working Version)"""
    DEBUG_PORT = 9222
    config = {
        'bin': Path(os.getenv('PROGRAMFILES')) / 'Google/Chrome/Application/chrome.exe',
        'user_data': Path(os.getenv('LOCALAPPDATA')) / 'Google/Chrome/User Data'
    }

    def log(message):
        """Debugging helper (remove when working)"""
        print(f"[DEBUG] {message}")

    # 1. Kill Chrome using original script's method
    log("Closing existing Chrome instances...")
    subprocess.run(f'taskkill /F /IM chrome.exe',
                  check=False, shell=True,
                  stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL)
    time.sleep(2)  # Increased sleep for process cleanup

    # 2. Launch with original script's EXACT parameters
    log("Starting Chrome...")
    args = [
        str(config['bin']),
        '--restore-last-session',  # CRUCIAL FOR COOKIE LOADING
        f'--remote-debugging-port={DEBUG_PORT}',
        '--remote-allow-origins=*',
        '--headless',  # Original uses simple headless mode
        f'--user-data-dir={config["user_data"]}'
    ]
    log(f"Launching with args: {' '.join(args)}")
    browser_proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,  # Capture output for debugging
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        # 3. Extended initialization wait
        log("Waiting for Chrome init...")
        time.sleep(5)  # Headless needs longer to load cookies

        # 4. Verify debug port accessibility
        log("Checking debug port...")
        try:
            debug_info = requests.get(f'http://localhost:{DEBUG_PORT}/json', timeout=5).json()
            log(f"Found {len(debug_info)} debug targets")
            if not debug_info:
                raise RuntimeError("No debug targets detected")
        except Exception as e:
            # Capture Chrome's output if connection failed
            log(f"Debug connection failed. Chrome output:\n{browser_proc.communicate()[0]}")
            raise

        # 5. Original WebSocket interaction pattern
        log("Connecting via WebSocket...")
        ws_url = debug_info[0]['webSocketDebuggerUrl'].strip()
        ws = websocket.create_connection(ws_url)  # Single connection

        try:  # PROPERLY STRUCTURED try/finally
            ws.send(json.dumps({'id': 1, 'method': 'Network.getAllCookies'}))
            response = json.loads(ws.recv())

            cookies = response.get('result', {}).get('cookies', [])
            log(f"Retrieved {len(cookies)} cookies")
            return cookies
        finally:
            ws.close()

    finally:  # Outer cleanup
        # 7. Clean termination
        log("Cleaning up...")
        browser_proc.terminate()
        try:
            browser_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            browser_proc.kill()
        subprocess.run(f'taskkill /F /IM chrome.exe',
                      check=False, shell=True,
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL)

def get_chrome_local_storage():
    """Access Chrome's local storage using proper key parsing"""
    import os
    import json
    import subprocess
    from pathlib import Path
    import base64
    import re

    def log(msg):
        print(f"[Storage Debug] {msg}")

    try:
        import plyvel
    except ImportError:
        try:
            log("Installing plyvel library...")
            subprocess.check_call(['pip', 'install', 'plyvel'])
            import plyvel
        except:
            print("You need to install plyvel manually, its a pain! Here's some scratch notes to do it:")
            notes = """git clone https://github.com/microsoft/vcpkg.git
cd vcpkg
bootstrap-vcpkg.bat

$env:VCPKG_ROOT = "C:\\path\\to\\vcpkg"
$env:PATH = "$env:VCPKG_ROOT;$env:PATH"


vcpkg install leveldb

$env:INCLUDE = "C:\\Users\\[USER]\\Documents\\vcpkg\\installed\\x64-windows\\include"
$env:LIB = "C:\\Users\\[USER]\\Documents\\vcpkg\\installed\\x64-windows\\lib"

python -m pip install plyvel"""
            print(notes)
            sys.exit()

    # Chrome paths
    user_data_dir = os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data')
    leveldb_path = os.path.join(user_data_dir, 'Default', 'Local Storage', 'leveldb')

    if not os.path.exists(leveldb_path):
        log(f"LevelDB path not found: {leveldb_path}")
        return {}

    all_storage = {}

    try:
        # Open the LevelDB database
        db = plyvel.DB(leveldb_path, create_if_missing=False)

        # Helper function to decode and parse keys
        def parse_key(raw_key):
            try:
                # Remove common prefixes
                if raw_key.startswith(b'\x00\x01'):
                    key_str = raw_key[2:].decode('utf-8')
                elif raw_key.startswith(b'\x01'):
                    key_str = raw_key[1:].decode('utf-8')
                else:
                    key_str = raw_key.decode('utf-8')

                # For META and METAACCESS keys
                if key_str.startswith(('META:', 'METAACCESS:', 'VERSION')):
                    return 'unknown', key_str

                # Split on null byte to separate domain and key
                parts = key_str.split('\x00')
                if len(parts) >= 2:
                    domain = parts[0].lstrip('_')  # Remove leading underscore if present
                    # Join remaining parts with null byte to preserve original key structure
                    key = '\x00'.join(parts[1:])
                    # Remove control characters from key while preserving structure
                    key = re.sub('[\x00-\x08\x0B\x0C\x0E-\x1F]', '', key)
                    return domain, key
                else:
                    return 'unknown', key_str
            except:
                return None, None

        # Helper function to decode values
        def decode_value(raw_value):
            try:
                # Try UTF-8 first
                value = raw_value.decode('utf-8')
                # Remove null bytes and control chars except newlines and spaces
                value = re.sub('[\x00-\x08\x0B\x0C\x0E-\x1F]', '', value)
                return value
            except:
                try:
                    # Try UTF-16
                    return raw_value.decode('utf-16')
                except:
                    # If all else fails, return base64
                    return base64.b64encode(raw_value).decode('utf-8')

        # Process all key-value pairs
        for key, value in db.iterator():
            try:
                domain, storage_key = parse_key(key)
                if not domain or not storage_key:
                    continue

                decoded_value = decode_value(value)
                if not decoded_value:
                    continue

                # Store in our result dictionary
                if domain not in all_storage:
                    all_storage[domain] = {}
                all_storage[domain][storage_key] = decoded_value

                log(f"Found key: {storage_key} for domain: {domain}")

            except Exception as e:
                log(f"Error processing entry: {e}")
                continue

        db.close()

    except Exception as e:
        log(f"Error accessing LevelDB: {e}")
        return {}

    # Clean up the domains by removing any remaining underscores
    cleaned_storage = {}
    for domain, values in all_storage.items():
        clean_domain = domain.lstrip('_')
        cleaned_storage[clean_domain] = values

    log(f"Found data for {len(cleaned_storage)} domains")
    return cleaned_storage

# ----- Firefox Cookies and Local Storage Functions -----

def get_firefox_local_storage(profile_dir=None):
    """
    Returns local storage data from Firefox's per-site storage databases.
    For each site folder in <profile_dir>/storage/default, this function looks for the
    ls/data.sqlite file and reads the key/value pairs from its "data" table.
    It returns a dictionary mapping origins (e.g. "https://example.com") to another
    dictionary of local storage key/value pairs.
    """
    # Auto-detect the profile directory if not provided.
    if profile_dir is None:
        if os.name == 'posix':
            base = os.path.expanduser('~/.mozilla/firefox')
        else:
            base = os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles')
        profiles = glob(os.path.join(base, '*default-release*'))
        if not profiles:
            profiles = glob(os.path.join(base, '*default*'))
        if not profiles:
            raise FileNotFoundError("Firefox profile not found")
        profile_dir = profiles[0]

    storage_dir = os.path.join(profile_dir, "storage", "default")
    ls_data = {}

    # Iterate over each site folder in the storage/default directory.
    for site_folder in glob(os.path.join(storage_dir, "*")):
        ls_db = os.path.join(site_folder, "ls", "data.sqlite")
        if os.path.exists(ls_db):
            # Convert the folder name to an origin string.
            # E.g., "https+++example.com" becomes "https://example.com"
            origin = os.path.basename(site_folder).replace("+++", "://")
            site_storage = {}
            try:
                conn = sqlite3.connect(ls_db)
                cur = conn.cursor()
                cur.execute("SELECT key, value FROM data")
                rows = cur.fetchall()
                for key, value in rows:
                    # Attempt to decode the value if it is stored as a BLOB.
                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8")
                        except Exception:
                            value = value.hex()
                    site_storage[key] = value
                conn.close()
                ls_data[origin] = site_storage
            except Exception as e:
                print(f"Error reading local storage from {ls_db}: {e}")
    return ls_data

def export_firefox_local_storage(output_file, profile_dir=None):
    """
    Exports local storage using the get_firefox_local_storage() function.
    """
    data = get_firefox_local_storage(profile_dir)
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Exported LocalStorage to {output_file}")

def import_local_storage_to_firefox(import_file, firefox_db=None):
    try:
        with open(import_file, 'r', encoding='utf-8') as f:
            storage_data = json.load(f)
    except Exception as e:
        print("Error reading local storage import file:", e)
        return

    if not storage_data:
        print("No local storage entries found in import file")
        return

    origins_imported = 0
    keys_imported = 0

    for origin, data in storage_data.items():
        # Derive folder name: replace "://" with "+++"
        folder_name = origin.replace("://", "+++")
        ls_dir = os.path.join(profile_dir, "storage", "default", folder_name, "ls")
        os.makedirs(ls_dir, exist_ok=True)
        db_path = os.path.join(ls_dir, "data.sqlite")

        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=OFF;")
            cur.execute("BEGIN TRANSACTION;")
            # Create tables if they do not exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS database(
                    origin TEXT NOT NULL,
                    usage INTEGER NOT NULL DEFAULT 0,
                    last_vacuum_time INTEGER NOT NULL DEFAULT 0,
                    last_analyze_time INTEGER NOT NULL DEFAULT 0,
                    last_vacuum_size INTEGER NOT NULL DEFAULT 0
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS data(
                    key TEXT PRIMARY KEY,
                    utf16_length INTEGER NOT NULL,
                    conversion_type INTEGER NOT NULL,
                    compression_type INTEGER NOT NULL,
                    last_access_time INTEGER NOT NULL DEFAULT 0,
                    value BLOB NOT NULL
                );
            """)
            # Insert (or update) the database metadata row
            cur.execute("INSERT OR REPLACE INTO database VALUES (?, ?, ?, ?, ?);",
                        (origin, 0, 0, 0, 0))

            for key, value in data.items():
                # Calculate the length of the value in UTF-16 code units
                utf16_length = len(value.encode('utf-16-le')) // 2
                conversion_type = 1
                compression_type = 0
                last_access_time = 0
                value_blob = value.encode('utf-8')
                try:
                    cur.execute("""
                        INSERT OR REPLACE INTO data
                        (key, utf16_length, conversion_type, compression_type, last_access_time, value)
                        VALUES (?, ?, ?, ?, ?, ?);
                    """, (key, utf16_length, conversion_type, compression_type, last_access_time, value_blob))
                    keys_imported += 1
                except Exception as e:
                    print(f"Error importing key '{key}' for origin {origin}: {e}")

            conn.commit()
            conn.close()
            origins_imported += 1
            print(f"Imported local storage for origin {origin} with {len(data)} entr{'y' if len(data)==1 else 'ies'}.")
        except Exception as e:
            print(f"Error processing origin {origin}: {e}")

    print(f"Imported local storage for {origins_imported} origin(s) with a total of {keys_imported} entr{'y' if keys_imported==1 else 'ies'}.")

def export_firefox_cookies(db=None):
    """
    Exports Firefox cookies in a format suitable for import.
    Returns a list of dictionaries, one per cookie.
    """
    if db is None:
        if globals().get('LINUX', False):
            profiles = glob(os.path.expanduser('~/.mozilla/firefox/*default-release*/cookies.sqlite'))
            if not profiles:
                profiles = glob(os.path.expanduser('~/.mozilla/firefox/*default*/cookies.sqlite'))
        else:
            profiles = glob(expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles\*default-release*\cookies.sqlite'))
            if not profiles:
                profiles = glob(expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles\*default*\cookies.sqlite'))
        if not profiles:
            raise FileNotFoundError("Firefox cookies database not found!")
        db = profiles[0]
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    query = """
      SELECT originAttributes, name, value, host, path, expiry, isSecure, isHttpOnly,
             inBrowserElement, sameSite, rawSameSite, schemeMap
      FROM moz_cookies
    """
    cookies = []
    for row in cur.execute(query):
        cookie = {
            "originAttributes": row[0],
            "name": row[1],
            "value": row[2],
            "host": row[3],
            "path": row[4],
            "expiry": row[5],
            "isSecure": row[6],
            "isHttpOnly": row[7],
            "inBrowserElement": row[8],
            "sameSite": row[9],
            "rawSameSite": row[10],
            "schemeMap": row[11],
            "baseDomain": row[3].lstrip('.') if row[3] else ""
        }
        cookies.append(cookie)
    conn.close()
    return cookies

# ----- Import Cookies into a Firefox Cookies Database -----
def import_cookies_to_firefox(import_file, firefox_db=None, default_host=None):
    """
    Imports cookies from a JSON file into a Firefox cookies database.
    """
    try:
        with open(import_file, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
    except Exception as e:
        print("Error reading the import file:", e)
        return

    if firefox_db is None:
        if globals().get('LINUX', False):
            profiles = glob(os.path.expanduser('~/.mozilla/firefox/*default-release*/cookies.sqlite'))
            if not profiles:
                profiles = glob(os.path.expanduser('~/.mozilla/firefox/*default*/cookies.sqlite'))
        else:
            profiles = glob(expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles\*default-release*\cookies.sqlite'))
            if not profiles:
                profiles = glob(expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles\*default*\cookies.sqlite'))
        if profiles:
            firefox_db = profiles[0]
            print("Using existing Firefox cookies DB at:", firefox_db)
        else:
            firefox_db = 'imported_cookies.sqlite'
            print("No existing Firefox cookies DB found; creating new DB at:", firefox_db)

    conn = sqlite3.connect(firefox_db)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='moz_cookies'")
    if not cur.fetchone():
        cur.execute("""
            CREATE TABLE moz_cookies (
                id INTEGER PRIMARY KEY,
                originAttributes TEXT NOT NULL DEFAULT '',
                name TEXT,
                value TEXT,
                host TEXT,
                path TEXT,
                expiry INTEGER,
                lastAccessed INTEGER,
                creationTime INTEGER,
                isSecure INTEGER,
                isHttpOnly INTEGER,
                inBrowserElement INTEGER DEFAULT 0,
                sameSite INTEGER DEFAULT 0,
                rawSameSite INTEGER DEFAULT 0,
                schemeMap INTEGER DEFAULT 0,
                isPartitionedAttributeSet INTEGER DEFAULT 0,
                CONSTRAINT moz_uniqueid UNIQUE (name, host, path, originAttributes)
            )
        """)
        print("Created new table 'moz_cookies' in the database.")
    now = int(time.time() * 1_000_000)
    imported_count = 0
    for cookie in cookies:
        name = cookie.get("name", "")
        value = cookie.get("value", "")
        host = cookie.get("host", default_host)
        if not host:
            print(f"Skipping cookie '{name}' because it lacks a host and no default was provided.")
            continue
        path = cookie.get("path", "/")
        expiry = cookie.get("expiry", 0)
        isSecure = cookie.get("isSecure", 0)
        isHttpOnly = cookie.get("isHttpOnly", 0)
        originAttributes = cookie.get("originAttributes", "")
        lastAccessed = now
        creationTime = now
        inBrowserElement = cookie.get("inBrowserElement", 0)
        sameSite = cookie.get("sameSite", 0)
        rawSameSite = cookie.get("rawSameSite", 0)
        schemeMap = cookie.get("schemeMap", 0)
        try:
            cur.execute("""
                INSERT INTO moz_cookies
                (originAttributes, name, value, host, path, expiry, lastAccessed, creationTime,
                 isSecure, isHttpOnly, inBrowserElement, sameSite, rawSameSite, schemeMap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (originAttributes, name, value, host, path, expiry,
                  lastAccessed, creationTime, isSecure, isHttpOnly,
                  inBrowserElement, sameSite, rawSameSite, schemeMap))
            imported_count += 1
        except Exception as e:
            print("Error inserting cookie", name, ":", e)
    conn.commit()
    conn.close()
    print("Imported", imported_count, "cookies into Firefox cookies DB at:", firefox_db)

# ----- New Function: Export All Sites' Local Storage -----
def export_all_sites_local_storage(profile_dir, output_file):
    """
    Scans the Firefox profile's storage/default directory for all sites,
    opens each ls/data.sqlite file, extracts key/value pairs from the "data" table,
    and writes them to a JSON file.
    """
    storage_default = os.path.join(profile_dir, "storage", "default")
    all_storage = {}

    if not os.path.exists(storage_default):
        print(f"Storage folder not found at {storage_default}")
        return

    site_folders = glob(os.path.join(storage_default, "*"))
    print(f"Found {len(site_folders)} site folder(s) in {storage_default}")

    for site_path in site_folders:
        print(f"Checking site folder: {site_path}")
        ls_db = os.path.join(site_path, "ls", "data.sqlite")
        if os.path.exists(ls_db):
            print(f"  Found ls db: {ls_db}")
            origin = os.path.basename(site_path).replace("+++", "://")
            site_storage = {}
            try:
                conn = sqlite3.connect(ls_db)
                cur = conn.cursor()
                cur.execute("SELECT key, value FROM data")
                rows = cur.fetchall()
                for key, value in rows:
                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8")
                        except Exception:
                            value = value.hex()
                    site_storage[key] = value
                conn.close()
                all_storage[origin] = site_storage
            except Exception as e:
                print(f"Error reading {ls_db}: {e}")
        else:
            print(f"  No ls db found in {site_path}")

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_storage, f, indent=2)
        print(f"Exported local storage for {len(all_storage)} site(s) to {output_file}")
    except Exception as e:
        print("Error writing to output file:", e)
def import_cookies_data(cookies, firefox_db=None, default_host=None):
    """
    Imports cookie objects (a list) into the Firefox cookies database.
    """
    # Auto-detect Firefox cookies DB if not provided.
    if firefox_db is None:
        if globals().get('LINUX', False):
            profiles = glob(os.path.expanduser('~/.mozilla/firefox/*default-release*/cookies.sqlite'))
            if not profiles:
                profiles = glob(os.path.expanduser('~/.mozilla/firefox/*default*/cookies.sqlite'))
        else:
            profiles = glob(expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles\*default-release*\cookies.sqlite'))
            if not profiles:
                profiles = glob(expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles\*default*\cookies.sqlite'))
        if profiles:
            firefox_db = profiles[0]
            print("Using existing Firefox cookies DB at:", firefox_db)
        else:
            firefox_db = 'imported_cookies.sqlite'
            print("No existing Firefox cookies DB found; creating new DB at:", firefox_db)
    conn = sqlite3.connect(firefox_db)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='moz_cookies'")
    if not cur.fetchone():
         cur.execute("""
            CREATE TABLE moz_cookies (
                id INTEGER PRIMARY KEY,
                originAttributes TEXT NOT NULL DEFAULT '',
                name TEXT,
                value TEXT,
                host TEXT,
                path TEXT,
                expiry INTEGER,
                lastAccessed INTEGER,
                creationTime INTEGER,
                isSecure INTEGER,
                isHttpOnly INTEGER,
                inBrowserElement INTEGER DEFAULT 0,
                sameSite INTEGER DEFAULT 0,
                rawSameSite INTEGER DEFAULT 0,
                schemeMap INTEGER DEFAULT 0,
                isPartitionedAttributeSet INTEGER DEFAULT 0,
                CONSTRAINT moz_uniqueid UNIQUE (name, host, path, originAttributes)
            )
         """)
         print("Created new table 'moz_cookies' in the database.")
    now = int(time.time() * 1_000_000)
    imported_count = 0
    for cookie in cookies:
         name = cookie.get("name", "")
         value = cookie.get("value", "")
         host = cookie.get("host", default_host)
         if not host:
             print(f"Skipping cookie '{name}' because it lacks a host and no default was provided.")
             continue
         path = cookie.get("path", "/")
         expiry = cookie.get("expiry", 0)
         isSecure = cookie.get("isSecure", 0)
         isHttpOnly = cookie.get("isHttpOnly", 0)
         originAttributes = cookie.get("originAttributes", "")
         lastAccessed = now
         creationTime = now
         inBrowserElement = cookie.get("inBrowserElement", 0)
         sameSite = cookie.get("sameSite", 0)
         rawSameSite = cookie.get("rawSameSite", 0)
         schemeMap = cookie.get("schemeMap", 0)
         try:
             cur.execute("""
                INSERT INTO moz_cookies
                (originAttributes, name, value, host, path, expiry, lastAccessed, creationTime,
                 isSecure, isHttpOnly, inBrowserElement, sameSite, rawSameSite, schemeMap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
             """, (originAttributes, name, value, host, path, expiry,
                   lastAccessed, creationTime, isSecure, isHttpOnly, inBrowserElement, sameSite, rawSameSite, schemeMap))
             imported_count += 1
         except Exception as e:
             print("Error inserting cookie", name, ":", e)
    conn.commit()
    conn.close()
    print("Imported", imported_count, "cookies into Firefox cookies DB at:", firefox_db)


def import_local_storage_data(storage_data, profile_dir):
    """
    Imports local storage data (a dict mapping origin to key/value dict) into Firefox’s per-site storage.
    """
    if profile_dir is None:
         if os.name == 'posix':
             base = os.path.expanduser('~/.mozilla/firefox')
         else:
             base = os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles')
         profiles = glob(os.path.join(base, '*default-release*'))
         if not profiles:
             profiles = glob(os.path.join(base, '*default*'))
         if not profiles:
             print("Firefox profile not found!")
             sys.exit(1)
         profile_dir = profiles[0]
    origins_imported = 0
    keys_imported = 0
    for origin, data in storage_data.items():
         folder_name = origin.replace("://", "+++")
         ls_dir = os.path.join(profile_dir, "storage", "default", folder_name, "ls")
         os.makedirs(ls_dir, exist_ok=True)
         db_path = os.path.join(ls_dir, "data.sqlite")
         try:
             conn = sqlite3.connect(db_path)
             cur = conn.cursor()
             cur.execute("PRAGMA foreign_keys=OFF;")
             cur.execute("BEGIN TRANSACTION;")
             cur.execute("""
                CREATE TABLE IF NOT EXISTS database(
                    origin TEXT NOT NULL,
                    usage INTEGER NOT NULL DEFAULT 0,
                    last_vacuum_time INTEGER NOT NULL DEFAULT 0,
                    last_analyze_time INTEGER NOT NULL DEFAULT 0,
                    last_vacuum_size INTEGER NOT NULL DEFAULT 0
                );
             """)
             cur.execute("""
                CREATE TABLE IF NOT EXISTS data(
                    key TEXT PRIMARY KEY,
                    utf16_length INTEGER NOT NULL,
                    conversion_type INTEGER NOT NULL,
                    compression_type INTEGER NOT NULL,
                    last_access_time INTEGER NOT NULL DEFAULT 0,
                    value BLOB NOT NULL
                );
             """)
             cur.execute("INSERT OR REPLACE INTO database VALUES (?, ?, ?, ?, ?);",
                         (origin, 0, 0, 0, 0))
             for key, value in data.items():
                  utf16_length = len(value.encode('utf-16-le')) // 2
                  conversion_type = 1
                  compression_type = 0
                  last_access_time = 0
                  value_blob = value.encode('utf-8')
                  try:
                      cur.execute("""
                         INSERT OR REPLACE INTO data
                         (key, utf16_length, conversion_type, compression_type, last_access_time, value)
                         VALUES (?, ?, ?, ?, ?, ?);
                      """, (key, utf16_length, conversion_type, compression_type, last_access_time, value_blob))
                      keys_imported += 1
                  except Exception as e:
                      print(f"Error importing key '{key}' for origin {origin}: {e}")
             conn.commit()
             conn.close()
             origins_imported += 1
             print(f"Imported local storage for origin {origin} with {len(data)} entr{'y' if len(data)==1 else 'ies'}.")
         except Exception as e:
             print(f"Error processing origin {origin}: {e}")
    print(f"Imported local storage for {origins_imported} origin(s) with a total of {keys_imported} entr{'y' if keys_imported==1 else 'ies'}.")


def import_all_from_json(import_file, firefox_db=None, default_host=None, profile_dir=None):
    """
    Imports both cookies and local storage from a single JSON file.

    The JSON file should have the structure:

    {
       "cookies": [ <list of cookie objects> ],
       "local_storage": { "<origin>": { "<key>": "<value>", ... }, ... }
    }
    """
    try:
         with open(import_file, 'r', encoding='utf-8') as f:
             data = json.load(f)
    except Exception as e:
         print("Error reading import file:", e)
         return
    if "cookies" in data:
         import_cookies_data(data["cookies"], firefox_db=firefox_db, default_host=default_host)
    else:
         print("No cookies found in import file.")
    if "local_storage" in data:
         import_local_storage_data(data["local_storage"], profile_dir=profile_dir)
    else:
         print("No local storage found in import file.")

# ----- Main Program with Argument Parsing -----
def main():

    usage_text = """\
    Export all cookies and local storage from Firefox:

    python script.py --firefox --output exported.json --local-storage

    Optionally, if you want to specify a particular Firefox profile directory:

    python script.py --firefox --output exported.json --local-storage --profile-dir "C:\\Users\\[USER]\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\[PROFILE-NAME].default-release"

    Import all cookies and local storage from one JSON file:

    python script.py --import-all imported.json

    Optionally, if you want to specify a particular Firefox profile directory:

    python script.py --import-all imported.json --profile-dir "C:\\Users\\[USER]\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\[PROFILE-NAME].default-release"
    """

    parser = argparse.ArgumentParser(
        description="Cookie management tool for Chrome/Firefox with import/export functionality.",
        usage=usage_text,  # Show the usage instructions on error
        formatter_class=argparse.RawTextHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--chrome', action='store_true', help="Use Chrome cookies")
    group.add_argument('--firefox', action='store_true', help="Use Firefox cookies (default)")
    parser.add_argument('--linux', action='store_true', help="Use Linux paths for Firefox cookies")
    parser.add_argument('--local-storage', action='store_true',
                        help="Also display or export Firefox local storage (if using Firefox)")
    # New unified import flag:
    parser.add_argument('--import-all', metavar='FILE',
                        help="Import cookies and local storage from a single JSON file")
    parser.add_argument('--output', help="Output file to export cookies (and optionally local storage) in JSON format")
    parser.add_argument('--db', help="Path to the cookie database file (Chrome or Firefox)")
    parser.add_argument('--default-host', help="Default host/domain to use for cookies missing that field")
    parser.add_argument('--profile-dir', help="Custom Firefox profile directory")
    parser.set_defaults(firefox=True)
    if len(sys.argv) == 1:
        print(usage_text)
        sys.exit(1)

    args = parser.parse_args()
#    if args.local_storage and args.chrome:
#        print("Sorry, local storage for chrome is broken! Please omit --local-storage")
#        sys.exit(1)
    global LINUX
    LINUX = args.linux

    # If --import-all is specified, import both cookies and local storage and exit.
    if args.import_all:
        if args.profile_dir:
            profile = args.profile_dir
        else:
            if os.name == 'posix':
                base = os.path.expanduser('~/.mozilla/firefox')
            else:
                base = os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles')
            profiles = glob(os.path.join(base, '*default-release*'))
            if not profiles:
                profiles = glob(os.path.join(base, '*default*'))
            if not profiles:
                print("Firefox profile not found!")
                sys.exit(1)
            profile = profiles[0]
        import_all_from_json(args.import_all, firefox_db=args.db, default_host=args.default_host, profile_dir=profile)
        return

    # If an output file is specified, export cookies (and optionally local storage) to that file.
    if args.output:
        result = {}
        if args.chrome:
            # Get Chrome data
            cookies = get_chrome_cookies()
            local_storage = {}
            if args.local_storage:
                local_storage = get_chrome_local_storage()
            result = {
                "cookies": cookies,
                "local_storage": local_storage
            }

            # Write to output file
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=4, default=str)
            print(f"Exported Chrome data to {args.output}")

        else:
            result["cookies"] = export_firefox_cookies(db=args.db)
        # If the --local-storage flag is provided, also export local storage.
        if args.local_storage and not args.chrome:  # Chrome local storage is already handled above
            if args.profile_dir:
                profile = args.profile_dir
            else:
                if os.name == 'posix':
                    base = os.path.expanduser('~/.mozilla/firefox')
                else:
                    base = os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles')
                profiles = glob(os.path.join(base, '*default-release*'))
                if not profiles:
                    profiles = glob(os.path.join(base, '*default*'))
                if not profiles:
                    print("Firefox profile not found!")
                    sys.exit(1)
                profile = profiles[0]
            result["local_storage"] = get_firefox_local_storage(profile)
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
            if args.local_storage:
                print(f"Exported cookies and local storage to {args.output}")
            else:
                print(f"Exported cookies to {args.output}")
        except Exception as e:
            print("Error writing to output file:", e)
        return
    if args.chrome:
        # Fetch cookies and local storage (if requested)
        cookies = get_chrome_cookies()
        local_storage = {}
        if args.local_storage:
            local_storage = get_chrome_local_storage()
        # Format for JSON output
        result = {
            "cookies": cookies,
            "local_storage": local_storage if args.local_storage else {}
        }

        if not args.output:  # Human-friendly output to console
            print("################# Chrome Cookies #############################")
            for cookie in cookies:
                print(f"{cookie['name']}: {cookie['value']}")
                print(f"  Domain: {cookie['domain']}")
                print(f"  Path: {cookie['path']}")
                print(f"  Expires: {datetime.datetime.fromtimestamp(cookie.get('expires', 0))}")
                print(f"  Secure: {cookie.get('secure', False)}")
                print(f"  HTTP Only: {cookie.get('httpOnly', False)}")
                print("-" * 50)

            if args.local_storage:
                print("\n################# Chrome Local Storage #############################")
                for domain, items in local_storage.items():
                    print(f"\nDomain: {domain}")
                    print("-" * 50)
                    for key, value in items.items():
                        # Truncate very long values
                        if len(str(value)) > 100:
                            value = str(value)[:100] + "..."
                        print(f"  {key}: {value}")
                    print("-" * 50)
        else:  # JSON output matches original format
            result = {
                "cookies": cookies,
                "local_storage": local_storage if args.local_storage else {}
            }
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=4, default=str)

    else:
        try:
            cookies = get_firefox_cookies(db=args.db)
            print("################# Firefox Cookies #############################")
            for name, (value, host) in cookies.items():
                print(f"{name} ({host}): {value}")
        except Exception as e:
            print("Error retrieving Firefox cookies:", e)
        if args.local_storage:
            try:
                if args.profile_dir:
                    profile = args.profile_dir
                else:
                    if os.name == 'posix':
                        base = os.path.expanduser('~/.mozilla/firefox')
                    else:
                        base = os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles')
                    profiles = glob(os.path.join(base, '*default-release*'))
                    if not profiles:
                        profiles = glob(os.path.join(base, '*default*'))
                    if not profiles:
                        print("Firefox profile not found!")
                        sys.exit(1)
                    profile = profiles[0]
                local_storage = get_firefox_local_storage(profile)
                print("################# Firefox Local Storage #############################")
                for key, value in local_storage.items():
                    print(f"{key}: {value}")
            except Exception as e:
                print("Error retrieving Firefox local storage:", e)

if __name__ == '__main__':
    main()

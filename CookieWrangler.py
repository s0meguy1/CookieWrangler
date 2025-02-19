#!/usr/bin/env python

"""
Export all cookies and local storage from Firefox:

python script.py --firefox --output exported.json --local-storage

Optionally, if you want to specify a particular Firefox profile directory:

python script.py --firefox --output exported.json --local-storage --profile-dir "C:\Users\[USER]\AppData\Roaming\Mozilla\Firefox\Profiles\[PROFILE-NAME].default-release"

Import all cookies and local storage from one JSON file:

python script.py --import-all imported.json

Optionally, if you want to specify a particular Firefox profile directory:

python script.py --import-all imported.json --profile-dir "C:\Users\[USER]\AppData\Roaming\Mozilla\Firefox\Profiles\[PROFILE-NAME].default-release"
"""

import argparse
import sqlite3
import json
import time
import os
from os.path import expandvars, dirname, join, exists
from glob import glob
import sys
from pathlib import Path

# ----- Chrome Cookies Functionality -----
def get_chrome_cookies(db=None):
    print("This still needs to be tested and is not working")
    print("Exiting...")
    exit()
    """
    Retrieves and decrypts Chrome cookies.
    Note: This works on Windows only and requires pywin32 and pycryptodomex.
    """
    from base64 import b64decode
    from win32.win32crypt import CryptUnprotectData  # pip install pywin32
    from Cryptodome.Cipher.AES import new, MODE_GCM  # pip install pycryptodomex

    if db is None:
        db = expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cookies')
    local_state_path = join(dirname(dirname(db)), 'Local State')
    with open(local_state_path, 'r', encoding='utf-8') as f:
        local_state = json.load(f)
        encrypted_key_b64 = local_state['os_crypt']['encrypted_key']
    key = CryptUnprotectData(b64decode(encrypted_key_b64)[5:])[1]
    conn = sqlite3.connect(db)
    conn.create_function('decrypt', 1,
                           lambda v: new(key, MODE_GCM, v[3:15]).decrypt(v[15:-16]).decode())
    cookies = dict(conn.execute("SELECT name, decrypt(encrypted_value) FROM cookies"))
    conn.close()
    return cookies

# ----- Firefox Cookies and Local Storage Functions -----
def get_firefox_cookies(db=None):
    """
    Retrieves a basic set of Firefox cookies.
    Returns a dictionary mapping cookie names to a tuple (value, host).
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
    cookies = {}
    for row in conn.execute("SELECT name, value, host FROM moz_cookies"):
        cookies[row[0]] = (row[1], row[2])
    conn.close()
    return cookies

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

python script.py --firefox --output exported.json --local-storage --profile-dir "C:\Users\[USER]\AppData\Roaming\Mozilla\Firefox\Profiles\[PROFILE-NAME].default-release"

Import all cookies and local storage from one JSON file:

python script.py --import-all imported.json

Optionally, if you want to specify a particular Firefox profile directory:

python script.py --import-all imported.json --profile-dir "C:\Users\[USER]\AppData\Roaming\Mozilla\Firefox\Profiles\[PROFILE-NAME].default-release"
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
    if len(sys.argv) == 1:
        print(usage_text)
        sys.exit(1)

    args = parser.parse_args()

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
        # Export cookies.
        if args.chrome:
            cookies = get_chrome_cookies(db=args.db)
            result["cookies"] = [{"name": k, "value": v} for k, v in cookies.items()]
        else:
            result["cookies"] = export_firefox_cookies(db=args.db)
        # If the --local-storage flag is provided, also export local storage.
        if args.local_storage:
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

    # If no output file is specified, simply display the cookies (and optionally local storage) to stdout.
    if args.chrome:
        try:
            cookies = get_chrome_cookies(db=args.db)
            print("################# Chrome Cookies #############################")
            for name, value in cookies.items():
                print(f"{name}: {value}")
        except Exception as e:
            print("Error retrieving Chrome cookies:", e)
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

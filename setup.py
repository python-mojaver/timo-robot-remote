"""ساخت تنظیمات اولیه و اطلاعات ورود روی کامپیوتر میزبان."""
import argparse
import getpass
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from server import new_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", help="Add your private HTTPS control URL, without a path")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    source = Path(__file__).with_name("config.json")
    if args.origin:
        value = args.origin.rstrip("/")
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            parser.error("Use an HTTPS origin such as https://computer.example.ts.net")
        if not source.exists():
            parser.error("Run setup.py without --origin first")
        config = json.loads(source.read_text(encoding="utf-8"))
        if value not in config["allowed_origins"]:
            config["allowed_origins"].append(value)
        source.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print("Private HTTPS origin added. Restart server.py.")
        return
    if source.exists():
        print("config.json already exists; existing credentials were preserved.")
        return
    if not 1024 <= args.port <= 65535:
        parser.error("Use a port between 1024 and 65535")
    password = getpass.getpass("Control password (at least 12 characters; Enter = generate): ")
    generated = not password
    if generated:
        password = secrets.token_urlsafe(16)
    if len(password) < 12:
        parser.error("The password must contain at least 12 characters")
    config = new_config(password, args.port)
    with source.open("x", encoding="utf-8") as output:
        json.dump(config, output, indent=2)
    try:
        os.chmod(source, 0o600)
    except OSError:
        pass
    print("Configuration created. Save these credentials privately.")
    if generated:
        print("CONTROL PASSWORD:", password)
    print("ROBOT TOKEN:", config["agent_token"])
    print("Start with: python server.py")


if __name__ == "__main__":
    main()

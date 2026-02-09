#!/usr/bin/env python3
"""devsync - Bidirectional dev environment sync over SSH."""

import argparse
import json
import os
import socket
import subprocess
import sys

CONFIG_DIR = os.path.expanduser("~/.config/devsync")
GLOBAL_PROFILES_FILE = os.path.join(CONFIG_DIR, "profiles.json")
LOCAL_PROFILES_FILE = "devsync.json"

DEFAULT_EXCLUDES = [
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".DS_Store", "*.pyc", ".env", "*.md",
]


def profiles_file():
    if os.path.exists(LOCAL_PROFILES_FILE):
        return LOCAL_PROFILES_FILE
    return GLOBAL_PROFILES_FILE


def load_profiles():
    path = profiles_file()
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_profiles(profiles, local=False):
    if local or os.path.exists(LOCAL_PROFILES_FILE):
        path = LOCAL_PROFILES_FILE
    else:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        path = GLOBAL_PROFILES_FILE
    with open(path, "w") as f:
        json.dump(profiles, f, indent=2, sort_keys=True)
        f.write("\n")


def build_rsync_cmd(src, dst, excludes, dry_run=False):
    cmd = ["rsync", "-avz", "--delete"]
    if dry_run:
        cmd.append("-n")
    for pattern in excludes:
        cmd.extend(["--exclude", pattern])
    cmd.extend([src, dst])
    return cmd


def ensure_trailing_slash(path):
    return path if path.endswith("/") else path + "/"


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def colorize_rsync_line(line):
    if line.startswith("deleting "):
        return f"{RED}- {line}{RESET}"
    if line.startswith("sending ") or line.startswith("receiving "):
        return f"{DIM}{line}{RESET}"
    if line.startswith("sent ") or line.startswith("total "):
        return f"{DIM}{line}{RESET}"
    if line == "" or line.startswith("building file list"):
        return f"{DIM}{line}{RESET}"
    if line.endswith("/"):
        return f"{DIM}  {line}{RESET}"
    return f"{GREEN}+ {line}{RESET}"


def run_rsync(cmd):
    print(f"  {YELLOW}{' '.join(cmd)}{RESET}\n")
    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        print(colorize_rsync_line(line))
    if result.stderr:
        for line in result.stderr.splitlines():
            print(f"{RED}{line}{RESET}")
    return result.returncode


def cmd_init(args):
    profiles = load_profiles()
    name = args.name

    if name in profiles and not args.force:
        print(f"Profile '{name}' already exists. Use --force to overwrite.")
        return 1

    excludes = list(DEFAULT_EXCLUDES)
    if args.exclude:
        excludes.extend(args.exclude)

    profiles[name] = {
        "host": args.host,
        "remote_path": args.remote,
        "local_path": args.local,
        "excludes": excludes,
    }
    save_profiles(profiles, local=args.local_config)
    where = LOCAL_PROFILES_FILE if args.local_config or os.path.exists(LOCAL_PROFILES_FILE) else GLOBAL_PROFILES_FILE
    print(f"Profile '{name}' created in {where}")
    return 0


def get_profile(profiles, name):
    if name not in profiles:
        print(f"Profile '{name}' not found. Run 'devsync list' to see profiles.")
        return None
    return profiles[name]


def cmd_push(args):
    profile = get_profile(load_profiles(), args.name)
    if not profile:
        return 1

    src = ensure_trailing_slash(profile["local_path"])
    dst = f"{profile['host']}:{ensure_trailing_slash(profile['remote_path'])}"

    print(f"{BOLD}{CYAN}Pushing{RESET} {src} -> {dst}")
    return run_rsync(build_rsync_cmd(src, dst, profile["excludes"]))


def cmd_pull(args):
    profile = get_profile(load_profiles(), args.name)
    if not profile:
        return 1

    src = f"{profile['host']}:{ensure_trailing_slash(profile['remote_path'])}"
    dst = ensure_trailing_slash(profile["local_path"])

    print(f"{BOLD}{CYAN}Pulling{RESET} {src} -> {dst}")
    return run_rsync(build_rsync_cmd(src, dst, profile["excludes"]))


def cmd_status(args):
    profile = get_profile(load_profiles(), args.name)
    if not profile:
        return 1

    local = ensure_trailing_slash(profile["local_path"])
    remote = f"{profile['host']}:{ensure_trailing_slash(profile['remote_path'])}"

    print(f"{BOLD}{CYAN}=== Changes to push (local -> remote) ==={RESET}")
    rc1 = run_rsync(build_rsync_cmd(local, remote, profile["excludes"], dry_run=True))

    print(f"\n{BOLD}{CYAN}=== Changes to pull (remote -> local) ==={RESET}")
    rc2 = run_rsync(build_rsync_cmd(remote, local, profile["excludes"], dry_run=True))

    return rc1 or rc2


def parse_known_hosts():
    """Parse ~/.ssh/known_hosts and return RSA entries as a list of dicts."""
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    if not os.path.exists(known_hosts):
        return []
    entries = []
    with open(known_hosts) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            hostnames, keytype, key_b64 = parts[0], parts[1], parts[2]
            if "ssh-rsa" not in keytype:
                continue
            # hostnames can be comma-separated (e.g. "host,1.2.3.4")
            for h in hostnames.split(","):
                h = h.strip("[]")  # bracketed [host]:port form
                entries.append({"host": h, "keytype": keytype})
    return entries


def probe_ssh(host, port=22, timeout=0.5):
    """Try to connect to an SSH port and grab the banner."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            banner = s.recv(256).decode("utf-8", errors="replace").strip()
            return banner
    except (OSError, socket.timeout):
        return None


def discover_lan_hosts():
    """Use arp table to find hosts on the local network with SSH open."""
    try:
        result = subprocess.run(
            ["arp", "-a"], capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        return []
    hosts = []
    for line in result.stdout.splitlines():
        # macOS: host (ip) at mac on iface ...
        # Linux: host (ip) at mac [ether] on iface
        paren_start = line.find("(")
        paren_end = line.find(")")
        if paren_start == -1 or paren_end == -1:
            continue
        ip = line[paren_start + 1:paren_end]
        if ip.startswith("224.") or ip.startswith("255.") or ip.endswith(".255"):
            continue
        hosts.append(ip)
    return hosts


def cmd_scan(args):
    rsa_hosts = parse_known_hosts()

    if rsa_hosts:
        print("Trusted RSA hosts (from known_hosts):\n")
        seen = set()
        for entry in rsa_hosts:
            h = entry["host"]
            if h in seen:
                continue
            seen.add(h)
            # try to resolve a hostname for bare IPs
            label = h
            try:
                name, _, _ = socket.gethostbyaddr(h)
                if name != h:
                    label = f"{h} ({name})"
            except (socket.herror, socket.gaierror, OSError):
                pass
            reachable = probe_ssh(h)
            status = f"  SSH: {reachable}" if reachable else "  SSH: unreachable"
            print(f"  {label}  {status}")
        return 0

    print("No trusted RSA hosts found in known_hosts.")
    print("Scanning local network for SSH services...\n")

    lan_hosts = discover_lan_hosts()
    if not lan_hosts:
        print("  No hosts found in ARP table.")
        return 0

    found = 0
    for ip in lan_hosts:
        banner = probe_ssh(ip)
        if banner:
            try:
                name, _, _ = socket.gethostbyaddr(ip)
                label = f"{ip} ({name})"
            except (socket.herror, socket.gaierror, OSError):
                label = ip
            print(f"  {label}")
            print(f"    {banner}")
            found += 1

    if not found:
        print("  No SSH services found on local network.")
    else:
        print(f"\n{found} host(s) with SSH open. Connect with:")
        print("  ssh user@<host>   (to add to known_hosts)")
        print("  devsync scan      (to verify)")

    return 0


HELP_TEXT = """\
devsync - Bidirectional dev environment sync over SSH

Commands:

  init      Create a new sync profile
  push      Sync files from local machine to remote
  pull      Sync files from remote machine to local
  status    Preview what would change (dry-run both directions)
  scan      Find trusted SSH hosts or discover SSH on local network
  list      Show all configured profiles
  remove    Delete a profile
  help      Show this help with examples

Examples:

  Set up a new profile:
    devsync init myproject --host cmoore@192.168.1.187 --remote /Users/cmoore/Code/myproject --local ~/Documents/Github/myproject

  Set up a profile with extra excludes:
    devsync init myproject --host cmoore@192.168.1.187 --remote /Users/cmoore/Code/myproject --local ~/Documents/Github/myproject --exclude "*.xcuserstate" --exclude "Pods"

  Overwrite an existing profile:
    devsync init myproject --host cmoore@192.168.1.187 --remote /path --local /path --force

  Push local changes to the remote machine:
    devsync push myproject

  Pull remote changes to the local machine:
    devsync pull myproject

  See what's different without syncing:
    devsync status myproject

  Find SSH hosts you can sync with:
    devsync scan

  List all your profiles:
    devsync list

  Remove a profile you no longer need:
    devsync remove myproject

Typical workflow:
  1. devsync scan              (find your other machine)
  2. devsync init <name> ...   (set up a profile)
  3. devsync push <name>       (send files over)
  4. ... work on the other machine ...
  5. devsync pull <name>       (bring changes back)

Config:
  Global: ~/.config/devsync/profiles.json
  Local:  ./devsync.json (takes priority, easy to edit with vim)

  Use --local-config with init to create a devsync.json in the current directory.
  If devsync.json exists in the current directory, all commands use it automatically.
"""


def cmd_help(args):
    print(HELP_TEXT)
    return 0


def cmd_list(args):
    profiles = load_profiles()
    if not profiles:
        print("No profiles configured. Run 'devsync init' to create one.")
        return 0

    for name, p in sorted(profiles.items()):
        print(f"  {name}")
        print(f"    host:   {p['host']}")
        print(f"    remote: {p['remote_path']}")
        print(f"    local:  {p['local_path']}")
    return 0


def cmd_remove(args):
    profiles = load_profiles()
    name = args.name

    if name not in profiles:
        print(f"Profile '{name}' not found.")
        return 1

    del profiles[name]
    save_profiles(profiles)
    print(f"Profile '{name}' removed.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="devsync",
        description="Bidirectional dev environment sync over SSH",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Create a new sync profile")
    p_init.add_argument("name", help="Profile name")
    p_init.add_argument("--host", required=True, help="SSH host (e.g. user@hostname)")
    p_init.add_argument("--remote", required=True, help="Remote path")
    p_init.add_argument("--local", required=True, help="Local path")
    p_init.add_argument("--exclude", action="append", help="Additional exclude pattern")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing profile")
    p_init.add_argument("--local-config", action="store_true", help="Save profile to ./devsync.json instead of global config")
    p_init.set_defaults(func=cmd_init)

    # push
    p_push = sub.add_parser("push", help="Sync local -> remote")
    p_push.add_argument("name", help="Profile name")
    p_push.set_defaults(func=cmd_push)

    # pull
    p_pull = sub.add_parser("pull", help="Sync remote -> local")
    p_pull.add_argument("name", help="Profile name")
    p_pull.set_defaults(func=cmd_pull)

    # status
    p_status = sub.add_parser("status", help="Dry-run diff both directions")
    p_status.add_argument("name", help="Profile name")
    p_status.set_defaults(func=cmd_status)

    # scan
    p_scan = sub.add_parser("scan", help="Find trusted RSA hosts or scan LAN for SSH")
    p_scan.set_defaults(func=cmd_scan)

    # help
    p_help = sub.add_parser("help", help="Show detailed help with examples")
    p_help.set_defaults(func=cmd_help)

    # list
    p_list = sub.add_parser("list", help="Show all profiles")
    p_list.set_defaults(func=cmd_list)

    # remove
    p_remove = sub.add_parser("remove", help="Delete a profile")
    p_remove.add_argument("name", help="Profile name")
    p_remove.set_defaults(func=cmd_remove)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)

"""Offline "what does this command do?" helper. Works with no internet and no AI key."""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

# name -> (summary, [(example, meaning)], caution or None)
DB: dict[str, tuple[str, list[tuple[str, str]], str | None]] = {
    "ls": ("Lists the files and folders in a directory.",
           [("ls -lah", "long list, including hidden files, with readable sizes"), ("ls -t", "newest first")], None),
    "cd": ("Moves you into another folder.",
           [("cd ~", "go to your home folder"), ("cd -", "jump back to the previous folder"), ("cd ..", "go up one level")], None),
    "pwd": ("Prints the folder you are currently in.", [("pwd", "show the current folder")], None),
    "cp": ("Copies files or folders.",
           [("cp a.txt b.txt", "copy a file"), ("cp -r dir/ backup/", "copy a whole folder")], "It overwrites the destination silently. Add -i to be asked first."),
    "mv": ("Moves or renames files and folders.",
           [("mv old.txt new.txt", "rename a file"), ("mv file.txt ~/Documents/", "move it")], "It overwrites the destination silently. Add -i to be asked first."),
    "rm": ("Deletes files. There is no Trash: deleted means gone.",
           [("rm file.txt", "delete one file"), ("rm -ri folder/", "delete a folder, asking about each item")],
           "Be very careful with -r (recursive) and -f (force). Double-check the path before pressing Enter."),
    "mkdir": ("Creates a new folder.", [("mkdir projects", "make a folder"), ("mkdir -p a/b/c", "make nested folders")], None),
    "rmdir": ("Removes an empty folder.", [("rmdir old", "remove it if it is empty")], None),
    "touch": ("Creates an empty file, or updates a file's timestamp.", [("touch notes.txt", "create notes.txt")], None),
    "cat": ("Prints a file's contents to the screen.", [("cat file.txt", "show the file"), ("cat a b > c", "join a and b into c")], None),
    "less": ("Lets you scroll through a long file. Press q to quit.", [("less /var/log/syslog", "read a log page by page")], None),
    "head": ("Shows the first lines of a file.", [("head -n 20 file.txt", "first 20 lines")], None),
    "tail": ("Shows the last lines of a file.", [("tail -f app.log", "follow a log as it grows (Ctrl+C to stop)")], None),
    "grep": ("Searches text for a pattern.",
             [("grep -rn 'TODO' .", "find TODO in every file below here, with line numbers"), ("grep -i error log.txt", "ignore case")], None),
    "find": ("Searches for files by name, type, size or date.",
             [("find . -name '*.py'", "all Python files below here"), ("find ~ -size +100M", "files over 100 MB")], None),
    "chmod": ("Changes who may read, write or run a file.",
              [("chmod +x script.sh", "make a script runnable"), ("chmod 644 file", "owner edits, everyone reads")],
              "Avoid chmod -R 777: it makes everything writable by everyone."),
    "chown": ("Changes a file's owner.", [("sudo chown $USER file", "make yourself the owner")], "Recursive use (-R) on system folders can break your system."),
    "sudo": ("Runs one command with administrator powers.", [("sudo apt update", "refresh the package list")],
             "Only use sudo with commands you understand. It can change or delete anything."),
    "apt": ("Installs, updates and removes software on Debian, Ubuntu and Zorin.",
            [("sudo apt update", "refresh the package list"), ("sudo apt install vlc", "install VLC"), ("sudo apt upgrade", "update installed software")], None),
    "df": ("Shows how full your disks are.", [("df -h", "sizes in readable units")], None),
    "du": ("Shows how much space files and folders use.", [("du -sh *", "size of everything here"), ("du -h --max-depth=1", "one level deep")], None),
    "ps": ("Lists running processes.", [("ps aux", "all processes"), ("ps aux | grep firefox", "find one")], None),
    "top": ("Live view of what is using your CPU and memory. Press q to quit.", [("top", "open the monitor")], None),
    "htop": ("A friendlier version of top (install with: sudo apt install htop).", [("htop", "open it")], None),
    "kill": ("Asks a process to stop, using its ID.", [("kill 1234", "ask process 1234 to quit"), ("kill -9 1234", "force it to stop")], "-9 gives the program no chance to save its work."),
    "tar": ("Packs or unpacks archive files.",
            [("tar -czf backup.tar.gz folder/", "create a compressed archive"), ("tar -xzf backup.tar.gz", "extract one")], None),
    "curl": ("Downloads from, or talks to, a web address.", [("curl -O https://example.com/file.zip", "download a file"), ("curl -I https://example.com", "show only the headers")],
             "Never pipe curl straight into a shell (curl ... | sh) unless you fully trust the source."),
    "wget": ("Downloads files from the web.", [("wget https://example.com/file.zip", "download a file")], None),
    "ssh": ("Opens a secure session on another computer.", [("ssh user@server", "log in to a server")], None),
    "scp": ("Copies files to or from another computer over SSH.", [("scp file.txt user@server:~/", "upload a file")], None),
    "ping": ("Checks whether another computer answers over the network.", [("ping -c 4 example.com", "send four test packets")], None),
    "man": ("Opens the manual page for a command. Press q to quit.", [("man ls", "read about ls")], None),
    "echo": ("Prints text.", [("echo hello", "print hello"), ("echo $HOME", "print a variable's value")], None),
    "history": ("Lists the commands you typed before.", [("history | tail", "the most recent ones")], None),
    "alias": ("Creates a shortcut for a longer command.", [("alias ll='ls -lah'", "type ll instead")], None),
    "systemctl": ("Controls background services.", [("systemctl status ssh", "is SSH running?"), ("sudo systemctl restart ssh", "restart it")], None),
    "journalctl": ("Reads the system log.", [("journalctl -b -p err", "errors since this boot")], None),
    "nano": ("A simple text editor in the terminal. Ctrl+O saves, Ctrl+X exits.", [("nano notes.txt", "edit a file")], None),
    "git": ("Tracks changes to your code and lets you share it.",
            [("git status", "what changed?"), ("git add . && git commit -m 'msg'", "save a snapshot"), ("git pull", "get the latest changes")], None),
    "ip": ("Shows and manages network settings.", [("ip a", "list network addresses")], None),
    "whoami": ("Prints your username.", [("whoami", "who am I?")], None),
    "clear": ("Clears the terminal screen (Ctrl+L does the same).", [("clear", "tidy up")], None),
    "which": ("Shows where a command lives on disk.", [("which python3", "find python3")], None),
    "uname": ("Prints system information.", [("uname -a", "everything")], None),
    "free": ("Shows memory usage.", [("free -h", "readable units")], None),
    "dd": ("Copies raw data between files and devices, often used to write disk images.", [],
           "dd can wipe a whole disk if you get of= wrong. Triple-check it, or use a tool like Disks instead."),
    "ln": ("Creates links (shortcuts) between files.", [("ln -s /path/to/file link", "make a symbolic link")], None),
    "sort": ("Sorts lines of text.", [("sort -u names.txt", "sort and remove duplicates")], None),
    "wc": ("Counts lines, words and characters.", [("wc -l file.txt", "count lines")], None),
}

_RISKY = [
    (re.compile(r"\brm\s+(-\w*[rf]\w*\s+)+(/|~|\*|/\*)(\s|$)"), "This looks like it deletes your whole system or home folder. Don't run it."),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"), "That's a fork bomb: it freezes your computer. Don't run it."),
    (re.compile(r"\bdd\b.*\bof=/dev/(sd|nvme|vd|mmc)"), "This writes straight onto a disk and will destroy its data."),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "This formats a drive and erases everything on it."),
    (re.compile(r">\s*/dev/(sd|nvme|vd|mmc)"), "This overwrites a disk with raw data."),
    (re.compile(r"\bchmod\s+(-\w+\s+)*[0-7]*777\b"), "777 lets everyone change these files. It's rarely the right fix."),
    (re.compile(r"(curl|wget)[^|]*\|\s*(sudo\s+)?(ba)?sh\b"), "This runs a script from the internet without you reading it first."),
]


@dataclass
class Explanation:
    command: str
    known: bool
    summary: str = ""
    examples: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def explain(cmdline: str) -> Explanation:
    cmdline = cmdline.strip()
    warnings = [msg for rx, msg in _RISKY if rx.search(cmdline)]
    try:
        words = shlex.split(cmdline)
    except ValueError:
        words = cmdline.split()
    # skip env assignments and sudo to find the real command
    idx, used_sudo = 0, False
    while idx < len(words) and (re.match(r"^\w+=", words[idx]) or words[idx] == "sudo"):
        used_sudo = used_sudo or words[idx] == "sudo"
        idx += 1
    name = words[idx].rsplit("/", 1)[-1] if idx < len(words) else ""
    entry = DB.get(name)
    if entry is None and not warnings:
        return Explanation(cmdline, False)
    summary, examples, caution = entry if entry else ("", [], None)
    if caution:
        warnings.append(caution)
    if used_sudo and name != "sudo":
        warnings.append("It runs with administrator rights, so mistakes can affect the whole system.")
    return Explanation(cmdline, entry is not None, summary, examples, list(dict.fromkeys(warnings)))

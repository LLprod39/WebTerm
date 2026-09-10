"""Local SSH/SFTP protocol fixture; never executes shell commands on the host."""
import asyncio
import json
from pathlib import Path
import asyncssh

root = Path(__file__).resolve().parents[1] / ".auth"
credentials = json.loads((root / "credentials.json").read_text())
class Server(asyncssh.SSHServer):
    def begin_auth(self, username):
        return True
    def password_auth_supported(self):
        return True
    def validate_password(self, username, password):
        return username == "qa" and password == credentials["sshPassword"]

def output(command):
    if command.startswith("echo "):
        return command[5:].strip("'\"") + "\n"
    if command.strip() == "pwd":
        return "/home/qa\n"
    if command.strip() == "whoami":
        return "qa\n"
    if "uname" in command:
        return "Linux qa-fixture 6.1.0 x86_64 GNU/Linux\n"
    if "os-release" in command:
        return 'ID=debian\nVERSION_ID="12"\nPRETTY_NAME="Debian GNU/Linux 12 (QA fixture)"\n'
    return "QA fixture: command accepted without host execution\n"

async def process(session):
    if session.command:
        session.stdout.write(output(session.command))
        session.exit(0)
        return
    session.stdout.write("WebTerm isolated QA terminal\r\nqa@fixture:~$ ")
    try:
        async for line in session.stdin:
            if line.strip() == "exit":
                session.exit(0)
                return
            session.stdout.write(output(line.strip()).replace("\n", "\r\n"))
            session.stdout.write("qa@fixture:~$ ")
    except (asyncssh.Error, BrokenPipeError):
        pass

async def main():
    async with asyncssh.create_server(Server, "127.0.0.1", 22391,
        server_host_keys=[str(root / "ssh_key")], process_factory=process,
        sftp_factory=lambda channel: asyncssh.SFTPServer(channel, chroot=str(root / "files"))):
        print("QA SSH/SFTP listening on 127.0.0.1:22391", flush=True)
        await asyncio.Future()
asyncio.run(main())

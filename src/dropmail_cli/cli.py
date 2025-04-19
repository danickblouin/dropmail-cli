import sys
import time
import uuid
import threading
from typing import Dict, List, Set

import requests
from colorama import Fore, init

init(autoreset=True)

POLL_INTERVAL = 5
GRAPHQL_FIELDS = """
    id
    fromAddr
    headerSubject
    text
"""


class DropmailClient:
    def __init__(self):
        try:
            self.sess = requests.Session()
            self.token = uuid.uuid4().hex
            self.endpoint = f"https://dropmail.me/api/graphql/{self.token}"
            self.headers = {
                "User-Agent": "Dropmail-CLI/1.0",
                "Content-Type": "application/json",
            }
            self.sess.headers.update(self.headers)

            self.session_id = None
            self.address = None
            self.expires_at = None
            self.seen: Set[str] = set()
            self.lock = threading.Lock()

            self.running = True
            self.start_session()
        except Exception as e:
            print(Fore.RED + f"[CRITICAL] Failed to initialize DropmailClient: {e}")
            sys.exit(1)

    def gql(self, query: str, variables: Dict = None) -> Dict:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        r = self.sess.post(self.endpoint, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise RuntimeError(data["errors"])
        return data["data"]

    def start_session(self):
        try:
            mutation = """
                mutation {
                    introduceSession {
                        id
                        expiresAt
                        addresses { address }
                    }
                }
            """
            data = self.gql(mutation)
            s = data["introduceSession"]
            self.session_id = s["id"]
            self.address = s["addresses"][0]["address"]
            self.expires_at = s["expiresAt"]
            self.seen.clear()

            print(f"\n{Fore.GREEN}[+] New temporary mailbox: {Fore.CYAN}{self.address}")
            print(f"{Fore.GREEN}    Session ID: {Fore.YELLOW}{self.session_id}")
            print(f"{Fore.GREEN}    Expires at: {Fore.MAGENTA}{self.expires_at}")
            print(f"{Fore.BLUE}Waiting for mail…\nType 'n' for new address, 'r' to reset, 'c' to copy email, 'q' to quit.\n")
        except Exception as e:
            print(Fore.RED + f"[!] Failed to start session: {e}")
            raise

    def fetch_mails(self) -> List[Dict]:
        try:
            query = f"""
                query ($id: ID!) {{
                    session(id: $id) {{
                        mails {{ {GRAPHQL_FIELDS} }}
                    }}
                }}
            """
            data = self.gql(query, {"id": self.session_id})
            session_info = data.get("session")
            if not session_info:
                return []
            return session_info["mails"]
        except Exception as e:
            print(Fore.RED + f"[!] Mail fetch failed: {e}")
            return []

    def display_mail(self, mail: Dict):
        print("\n" + Fore.YELLOW + "-" * 72)
        print(f"{Fore.CYAN}From   : {Fore.WHITE}{mail['fromAddr']}")
        print(f"{Fore.CYAN}Subject: {Fore.WHITE}{mail['headerSubject']}")
        print(f"{Fore.CYAN}Body   :\n{Fore.WHITE}{mail['text'].rstrip() or '<no plain-text part>'}")
        print(Fore.YELLOW + "-" * 72 + "\n")

    def poll_loop(self):
        while self.running:
            try:
                with self.lock:
                    mails = self.fetch_mails()
                    new_mails = [mail for mail in mails if mail["id"] not in self.seen]

                    for mail in new_mails:
                        self.seen.add(mail["id"])
                        self.display_mail(mail)

                    if new_mails:
                        print(f"{Fore.MAGENTA}[cmd]> ", end="", flush=True)
            except Exception as e:
                print(Fore.RED + f"[!] Error during polling: {e}")
            time.sleep(POLL_INTERVAL)

    def copy_to_clipboard(self):
        try:
            import pyperclip
            pyperclip.copy(self.address)
            print(Fore.GREEN + "[+] Email address copied to clipboard")
        except ImportError:
            print(Fore.RED + "[!] Install pyperclip for clipboard support")
        except Exception as e:
            print(Fore.RED + f"[!] Clipboard error: {e}")

    def input_loop(self):
        while self.running:
            try:
                cmd = input(f"{Fore.MAGENTA}[cmd]> ").strip().lower()
                with self.lock:
                    if cmd == "n":
                        print(Fore.MAGENTA + "[~] New address requested.")
                        try:
                            self.start_session()
                        except Exception as e:
                            print(Fore.RED + f"[!] Error creating new session: {e}")
                    elif cmd == "r":
                        print(Fore.CYAN + "[~] Resetting seen mail.")
                        self.seen.clear()
                    elif cmd == "c":
                        self.copy_to_clipboard()
                    elif cmd == "q":
                        print(Fore.RED + "[+] Quitting...")
                        self.running = False
                    else:
                        print(Fore.YELLOW + "[?] Commands: 'n' (new), 'r' (reset), 'c' (copy), 'q' (quit)")
            except EOFError:
                print(Fore.RED + "[!] Input closed. Exiting.")
                self.running = False
            except Exception as e:
                print(Fore.RED + f"[!] Input error: {e}")


def main():
    if sys.version_info < (3, 8):
        sys.exit("Run this with Python 3.8 or newer.")

    print(Fore.CYAN + "[*] Launching Dropmail client...")
    client = DropmailClient()

    poll_thread = threading.Thread(target=client.poll_loop, daemon=True)
    poll_thread.start()

    client.input_loop()
    poll_thread.join()


if __name__ == "__main__":
    main()

import hashlib
import time
import json
import socket
import threading
import sys
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────
#  BLOCK
# ─────────────────────────────────────────────

class Block:
    """
    A single block in the chain.

    Fields that go into the hash:
      index       – position in the chain (0 = genesis)
      timestamp   – unix time when mined
      data        – arbitrary payload (transactions, messages, etc.)
      prev_hash   – SHA-256 hash of the previous block  ← the "chain" part
      nonce       – number we increment during proof-of-work
    """

    def __init__(self, index: int, data, prev_hash: str):
        self.index     = index
        self.timestamp = time.time()
        self.data      = data
        self.prev_hash = prev_hash
        self.nonce     = 0
        self.hash      = self.compute_hash()

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    def compute_hash(self) -> str:
        """
        Serialise every field to JSON (deterministic) and return its
        SHA-256 hex digest.  Even a 1-character change flips the hash
        completely – that's what makes tampering detectable.
        """
        block_string = json.dumps({
            "index"    : self.index,
            "timestamp": self.timestamp,
            "data"     : self.data,
            "prev_hash": self.prev_hash,
            "nonce"    : self.nonce,
        }, sort_keys=True)          # sort_keys → same string every time

        return hashlib.sha256(block_string.encode()).hexdigest()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Block":
        block = cls(data["index"], data["data"], data["prev_hash"])
        block.timestamp = data["timestamp"]
        block.nonce = data["nonce"]
        block.hash = data["hash"]
        return block

    # ------------------------------------------------------------------
    # Proof-of-Work
    # ------------------------------------------------------------------

    def mine(self, difficulty: int) -> None:
        """
        Keep incrementing nonce until the hash starts with `difficulty`
        leading zeros, e.g. difficulty=3 → "000a4f…"

        Cost grows exponentially: each extra zero makes it ~16× harder
        (hex digits, so base 16).
        """
        target = "0" * difficulty

        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash   = self.compute_hash()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"\n┌─ Block #{self.index} {'(genesis)' if self.index == 0 else ''}\n"
            f"│  hash      : {self.hash}\n"
            f"│  prev_hash : {self.prev_hash}\n"
            f"│  nonce     : {self.nonce}\n"
            f"│  data      : {self.data}\n"
            f"└─ timestamp : {self.timestamp}"
        )


# ─────────────────────────────────────────────
#  BLOCKCHAIN
# ─────────────────────────────────────────────

class Blockchain:
    """
    An ordered list of Blocks where every block references the hash of
    the one before it.  Tampering with any block breaks the chain from
    that point forward – which is exactly what validation catches.
    """

    DIFFICULTY = 4          # leading zeros required  (try 5 to feel the slowdown)

    def __init__(self):
        self.chain: list[Block] = []
        self.p2p_node: Optional["P2PNode"] = None
        self._create_genesis_block()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_genesis_block(self) -> None:
        """
        Block 0 – the only block with no real predecessor.
        prev_hash is set to a string of zeros by convention.
        """
        genesis = Block(index=0, data="Genesis Block", prev_hash="0" * 64)
        genesis.mine(self.DIFFICULTY)
        self.chain.append(genesis)
        print(f"⛏  Genesis block mined  (nonce={genesis.nonce})")

    @property
    def latest_block(self) -> Block:
        return self.chain[-1]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_block(self, data) -> Block:
        """
        Create a new block, link it to the chain tip, mine it, append.
        """
        new_block = Block(
            index     = len(self.chain),
            data      = data,
            prev_hash = self.latest_block.hash,   # ← SHA-256 link
        )
        new_block.mine(self.DIFFICULTY)
        self.chain.append(new_block)
        print(f"⛏  Block #{new_block.index} mined  (nonce={new_block.nonce})")
        if self.p2p_node is not None:
            self.p2p_node.broadcast_new_block(new_block)
        return new_block

    def to_dict(self) -> List[Dict[str, Any]]:
        return [
            {
                "index": block.index,
                "timestamp": block.timestamp,
                "data": block.data,
                "prev_hash": block.prev_hash,
                "nonce": block.nonce,
                "hash": block.hash,
            }
            for block in self.chain
        ]

    @classmethod
    def from_dict(cls, chain_data: List[Dict[str, Any]]) -> "Blockchain":
        blockchain = cls.__new__(cls)
        blockchain.chain = [Block.from_dict(block_data) for block_data in chain_data]
        blockchain.p2p_node = None
        return blockchain

    def replace_chain(self, new_chain: List[Block]) -> bool:
        if len(new_chain) <= len(self.chain):
            return False
        if not self.is_valid_chain(new_chain):
            return False
        self.chain = new_chain
        print("🔄 Replaced local chain with a longer valid chain")
        return True

    def is_valid_chain(self, chain: List[Block]) -> bool:
        if not chain:
            return False
        for i in range(1, len(chain)):
            current = chain[i]
            previous = chain[i - 1]
            if current.hash != current.compute_hash():
                return False
            if current.prev_hash != previous.hash:
                return False
        return True

    def register_p2p_node(self, p2p_node: "P2PNode") -> None:
        self.p2p_node = p2p_node

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def is_valid(self) -> bool:
        """
        Walk the chain and verify two things for every non-genesis block:

          1. Hash integrity  – the stored hash matches a freshly computed one.
             If someone edits block.data after mining, this fails.

          2. Chain linkage   – prev_hash matches the actual hash of the
             preceding block.  If someone inserts or reorders blocks, this fails.
        """
        for i in range(1, len(self.chain)):
            current  = self.chain[i]
            previous = self.chain[i - 1]

            # 1 – Recompute and compare
            if current.hash != current.compute_hash():
                print(f"✗ Block #{i}: hash mismatch (data was tampered)")
                return False

            # 2 – Check the link
            if current.prev_hash != previous.hash:
                print(f"✗ Block #{i}: broken link to block #{i-1}")
                return False

        return True

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_chain(self) -> None:
        for block in self.chain:
            print(block)

    def __len__(self) -> int:
        return len(self.chain)


# ─────────────────────────────────────────────
#  P2P NETWORK
# ─────────────────────────────────────────────

class P2PNode:
    BUFFER_SIZE = 65536

    def __init__(self, blockchain: Blockchain, host: str = "127.0.0.1", port: int = 5000, peers: Optional[List[str]] = None):
        self.blockchain = blockchain
        self.host = host
        self.port = port
        self.peers = set()
        # peers the node should try to connect to (initial targets)
        self.known_peers_to_try = set(peers or [])
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.running = False
        self.lock = threading.Lock()
        blockchain.register_p2p_node(self)

    def start(self) -> None:
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        self.running = True
        threading.Thread(target=self._accept_peers, daemon=True).start()
        print(f"🌐 P2P node listening on {self.host}:{self.port}")
        # Start a background thread that will attempt to connect to known peers
        threading.Thread(target=self._connect_with_retry, daemon=True).start()

    def stop(self) -> None:
        self.running = False
        try:
            self.server_socket.close()
        except OSError:
            pass

    def _accept_peers(self) -> None:
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_peer, args=(conn, addr), daemon=True).start()
            except OSError:
                break

    def _handle_peer(self, conn: socket.socket, addr) -> None:
        with conn:
            try:
                raw = conn.recv(self.BUFFER_SIZE)
                if not raw:
                    return
                message = json.loads(raw.decode("utf-8"))
                response = self._process_message(message, addr)
                if response is not None:
                    conn.sendall(json.dumps(response).encode("utf-8"))
            except (json.JSONDecodeError, ConnectionResetError):
                return

    def _process_message(self, message: Dict[str, Any], addr) -> Optional[Dict[str, Any]]:
        message_type = message.get("type")

        if message_type == "PEER_INTRODUCE":
            sender = message.get("peer")
            peer_list = message.get("peers", [])
            if sender and sender != f"{self.host}:{self.port}":
                self.peers.add(sender)
            for peer in peer_list:
                if peer != f"{self.host}:{self.port}":
                    self.peers.add(peer)
            return {"type": "PEER_ACK", "peers": list(self.peers)}

        if message_type == "CHAIN_REQUEST":
            return {"type": "CHAIN_RESPONSE", "chain": self.blockchain.to_dict()}

        if message_type == "CHAIN_RESPONSE":
            chain_data = message.get("chain", [])
            try:
                new_chain = Blockchain.from_dict(chain_data)
                if len(new_chain.chain) > len(self.blockchain.chain) and new_chain.is_valid():
                    self.blockchain.replace_chain(new_chain.chain)
            except Exception:
                pass
            return None

        if message_type == "NEW_BLOCK":
            block_data = message.get("block")
            if block_data is None:
                return None
            block = Block.from_dict(block_data)
            # If the new block extends our chain cleanly, accept it.
            if block.index == len(self.blockchain.chain) and block.prev_hash == self.blockchain.latest_block.hash:
                if block.hash == block.compute_hash() and block.hash.startswith("0" * self.blockchain.DIFFICULTY):
                    self.blockchain.chain.append(block)
                    print(f"📥 Accepted new block #{block.index} from peer")
            # If the incoming block's index is >= our chain length or there's a prev_hash mismatch,
            # request the full chain from the peer so we can perform a proper replacement sync.
            elif block.index >= len(self.blockchain.chain) or block.prev_hash != self.blockchain.latest_block.hash:
                sender = message.get("sender")
                if sender:
                    self.request_chain(sender)
                else:
                    self.request_chain(addr[0] + ":" + str(addr[1]))
            return None

        return None

    def _send_message(self, peer: str, message: Dict[str, Any], timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        host, port = peer.split(":")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            try:
                sock.connect((host, int(port)))
                sock.sendall(json.dumps(message).encode("utf-8"))
                raw = sock.recv(self.BUFFER_SIZE)
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
            except (ConnectionRefusedError, socket.timeout, json.JSONDecodeError, OSError):
                return None

    def connect_to_peer(self, peer: str) -> bool:
        if peer == f"{self.host}:{self.port}":
            return False

        response = self._send_message(peer, {"type": "PEER_INTRODUCE", "peer": f"{self.host}:{self.port}", "peers": list(self.peers)})
        if response is None or response.get("type") != "PEER_ACK":
            print(f"⚠️ Failed to connect to peer {peer}")
            return False

        self.peers.add(peer)
        for remote_peer in response.get("peers", []):
            if remote_peer != f"{self.host}:{self.port}":
                self.peers.add(remote_peer)

        self.request_chain(peer)
        print(f"🔗 Connected to peer {peer}")
        return True

    def request_chain(self, peer: str) -> bool:
        response = self._send_message(peer, {"type": "CHAIN_REQUEST"})
        if response and response.get("type") == "CHAIN_RESPONSE":
            chain_data = response.get("chain", [])
            try:
                new_chain = Blockchain.from_dict(chain_data)
                if len(new_chain.chain) > len(self.blockchain.chain) and new_chain.is_valid():
                    self.blockchain.replace_chain(new_chain.chain)
                    return True
            except Exception:
                pass
        return False

    def _connect_with_retry(self, interval: float = 1.0, max_attempts: int = 15) -> None:
        """Background worker that attempts to connect to known peers until success or max attempts."""
        attempts = {peer: 0 for peer in list(self.known_peers_to_try)}
        while self.running and self.known_peers_to_try:
            for peer in list(self.known_peers_to_try):
                if peer in self.peers:
                    self.known_peers_to_try.discard(peer)
                    attempts.pop(peer, None)
                    continue

                if attempts.get(peer, 0) >= max_attempts:
                    print(f"⚠️ Giving up on peer {peer} after {max_attempts} attempts")
                    self.known_peers_to_try.discard(peer)
                    attempts.pop(peer, None)
                    continue

                success = self.connect_to_peer(peer)
                attempts[peer] = attempts.get(peer, 0) + 1
                if success:
                    self.known_peers_to_try.discard(peer)
                    attempts.pop(peer, None)

            time.sleep(interval)

    def broadcast_new_block(self, block: Block) -> None:
        message = {"type": "NEW_BLOCK", "sender": f"{self.host}:{self.port}", "block": {
            "index": block.index,
            "timestamp": block.timestamp,
            "data": block.data,
            "prev_hash": block.prev_hash,
            "nonce": block.nonce,
            "hash": block.hash,
        }}
        for peer in list(self.peers):
            self._send_message(peer, message)


# ─────────────────────────────────────────────
#  DEMO
# ─────────────────────────────────────────────

def demo():
    print("=" * 60)
    print("  Simple Python Blockchain  (difficulty=4)")
    print("=" * 60)

    # ── Build the chain ───────────────────────────────────────────────
    bc = Blockchain()

    bc.add_block({
        "sender"   : "Alice",
        "receiver" : "Bob",
        "amount"   : 50,
    })

    bc.add_block({
        "sender"   : "Bob",
        "receiver" : "Carol",
        "amount"   : 20,
    })

    bc.add_block("Deploy smart contract 0xDEADBEEF")

    print("\n──── Chain (" + str(len(bc)) + " blocks) ────")
    bc.print_chain()

    # ── Validate (should pass) ────────────────────────────────────────
    print("\n──── Validation ────")
    print("Valid?", bc.is_valid())   # True

    # ── Tamper with block #1 and re-validate ─────────────────────────
    print("\n──── Tampering with Block #1 ────")
    bc.chain[1].data = {"sender": "Alice", "receiver": "Bob", "amount": 9999}
    print("Valid after tampering?", bc.is_valid())  # False


if __name__ == "__main__":
    demo()

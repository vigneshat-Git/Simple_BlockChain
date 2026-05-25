"""
wallet.py — Cryptographic wallet: key generation, addresses, signing
─────────────────────────────────────────────────────────────────────
Mirrors real-world blockchain wallets (Bitcoin / Ethereum style):

  Private key  →  (ECDSA secp256k1)  →  Public key
  Public key   →  (SHA-256 + RIPEMD-160 + Base58Check)  →  Address
  Transaction  →  (sign with private key)  →  Signature
  Signature    →  (verify with public key)  →  True / False

Nothing here requires a network connection — wallets are purely local
cryptographic objects.  The blockchain layer imports Transaction and
calls Transaction.verify() before including a tx in a block.
"""

import hashlib
import json
import base64
import os
import time
from typing import Optional

# secp256k1 — the same curve Bitcoin and Ethereum use
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature


# ─────────────────────────────────────────────────────────────────────
#  ADDRESS DERIVATION  (Bitcoin-style)
# ─────────────────────────────────────────────────────────────────────
#
#  Real Bitcoin address pipeline (simplified here):
#
#    public key bytes
#        │  SHA-256
#        ▼
#    32-byte digest
#        │  RIPEMD-160
#        ▼
#    20-byte "public key hash"
#        │  version prefix (0x00) + 4-byte checksum + Base58
#        ▼
#    human-readable address  e.g. "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf"
#
#  We implement the core SHA-256 → RIPEMD-160 → Base58Check pipeline
#  below.  The result looks and behaves like a real Bitcoin address.

BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_encode(data: bytes) -> str:
    """Encode bytes to Base58 (no padding character '0')."""
    # Count leading zero bytes — each becomes '1' in Base58
    count = 0
    for byte in data:
        if byte == 0:
            count += 1
        else:
            break

    num = int.from_bytes(data, "big")
    result = []
    while num > 0:
        num, remainder = divmod(num, 58)
        result.append(BASE58_ALPHABET[remainder : remainder + 1])

    result.reverse()
    return (b"1" * count + b"".join(result)).decode("ascii")


def _checksum(payload: bytes) -> bytes:
    """4-byte checksum: SHA-256(SHA-256(payload))[:4]."""
    first  = hashlib.sha256(payload).digest()
    second = hashlib.sha256(first).digest()
    return second[:4]


def public_key_to_address(public_key_bytes: bytes) -> str:
    """
    Derive a Base58Check address from a compressed public key.

    Steps
    ─────
    1. SHA-256 of the public key bytes
    2. RIPEMD-160 of that digest  →  20-byte "pubkey hash"
    3. Prepend version byte 0x00  (mainnet P2PKH prefix)
    4. Append 4-byte checksum
    5. Base58 encode the whole thing
    """
    # Step 1-2
    sha256_digest = hashlib.sha256(public_key_bytes).digest()
    ripemd160     = hashlib.new("ripemd160", sha256_digest).digest()

    # Step 3-4
    versioned = b"\x00" + ripemd160
    full      = versioned + _checksum(versioned)

    # Step 5
    return _base58_encode(full)


# ─────────────────────────────────────────────────────────────────────
#  WALLET
# ─────────────────────────────────────────────────────────────────────

class Wallet:
    """
    A secp256k1 key pair with a derived address.

    Attributes
    ──────────
    private_key   cryptography PrivateKey object (never leave the machine)
    public_key    cryptography PublicKey object
    address       Base58Check string  e.g. "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"
    """

    def __init__(self):
        # Generate a cryptographically secure random 256-bit private key
        # on the secp256k1 curve (same parameters as Bitcoin / Ethereum)
        self._private_key = ec.generate_private_key(
            ec.SECP256K1(), default_backend()
        )
        self._public_key  = self._private_key.public_key()
        self.address      = public_key_to_address(self._public_key_bytes())

    # ── Key serialisation ─────────────────────────────────────────────

    def _public_key_bytes(self) -> bytes:
        """Compressed SEC1 encoding of the public key (33 bytes)."""
        return self._public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.CompressedPoint,
        )

    def public_key_hex(self) -> str:
        """Public key as a hex string (easier to print / share)."""
        return self._public_key_bytes().hex()

    def private_key_hex(self) -> str:
        """
        Raw 32-byte private key scalar as hex.
        ⚠ NEVER share this — whoever has it controls the wallet.
        """
        raw = self._private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        return raw.hex()

    # ── Persistence ───────────────────────────────────────────────────

    def save(self, path: str, password: Optional[str] = None) -> None:
        """
        Save the private key to disk (PEM format).
        If a password is supplied the key is encrypted with AES-256-CBC
        so the file is safe to store.  Without a password it is saved
        unencrypted — convenient for demos, dangerous in production.
        """
        if password:
            encryption = serialization.BestAvailableEncryption(
                password.encode()
            )
        else:
            encryption = serialization.NoEncryption()

        pem = self._private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            encryption,
        )
        with open(path, "wb") as f:
            f.write(pem)

    @classmethod
    def load(cls, path: str, password: Optional[str] = None) -> "Wallet":
        """Reconstruct a Wallet from a saved PEM file."""
        pw = password.encode() if password else None
        with open(path, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(), password=pw, backend=default_backend()
            )
        w = cls.__new__(cls)
        w._private_key = private_key
        w._public_key  = private_key.public_key()
        w.address      = public_key_to_address(w._public_key_bytes())
        return w

    # ── Signing ───────────────────────────────────────────────────────

    def sign(self, message: bytes) -> str:
        """
        Sign arbitrary bytes with the private key.

        Algorithm: ECDSA on secp256k1 with SHA-256 (same as Bitcoin Script OP_CHECKSIG).

        The raw DER signature is Base64-encoded for easy JSON embedding.
        Returns a Base64 string.
        """
        der_sig = self._private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        return base64.b64encode(der_sig).decode()

    # ── Static verification ───────────────────────────────────────────

    @staticmethod
    def verify(message: bytes, signature_b64: str,
               public_key_hex: str) -> bool:
        """
        Verify a signature without needing the private key — only the
        public key (which is public!) is required.

        Used by the blockchain to validate transactions before mining.
        Returns True if and only if the signature is authentic.
        """
        try:
            pub_bytes = bytes.fromhex(public_key_hex)
            public_key = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256K1(), pub_bytes
            )
            sig_bytes = base64.b64decode(signature_b64)
            public_key.verify(sig_bytes, message, ec.ECDSA(hashes.SHA256()))
            return True
        except (InvalidSignature, Exception):
            return False

    # ── Helpers ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Wallet(\n"
            f"  address    = {self.address}\n"
            f"  public_key = {self.public_key_hex()[:24]}…\n"
            f")"
        )


# ─────────────────────────────────────────────────────────────────────
#  TRANSACTION
# ─────────────────────────────────────────────────────────────────────

class Transaction:
    """
    A signed value transfer between two addresses.

    Lifecycle
    ─────────
    1. Sender builds a Transaction (sender_address, receiver_address, amount)
    2. Sender signs it with their Wallet                → tx.sign(wallet)
    3. Tx is broadcast to the network / added to mempool
    4. Miner calls tx.verify()                          → True/False
    5. If valid, the tx is included in the next Block
    6. Block is mined and appended to the chain

    The signature covers: sender, receiver, amount, timestamp, tx_id.
    Changing any of those fields after signing invalidates the signature.

    tx_id is deterministic: SHA-256 of the canonical payload JSON.
    """

    def __init__(
        self,
        sender_address:   str,
        receiver_address: str,
        amount:           float,
        sender_public_key: str = "",   # needed for verification
    ):
        self.sender_address    = sender_address
        self.receiver_address  = receiver_address
        self.amount            = amount
        self.sender_public_key = sender_public_key
        self.timestamp         = time.time()
        self.tx_id             = self._compute_id()
        self.signature: Optional[str] = None

    # ── Payload ───────────────────────────────────────────────────────

    def _payload(self) -> bytes:
        """
        The canonical bytes that get signed / verified.

        CRITICAL: every field that must be immutable after signing is
        included here.  Omitting `amount` would let an attacker change
        it freely; omitting `tx_id` would allow replay attacks.
        """
        d = {
            "tx_id"           : self.tx_id,
            "sender_address"  : self.sender_address,
            "receiver_address": self.receiver_address,
            "amount"          : self.amount,
            "timestamp"       : self.timestamp,
        }
        return json.dumps(d, sort_keys=True).encode()

    def _compute_id(self) -> str:
        """SHA-256 of the core fields (no signature, no public key)."""
        d = {
            "sender_address"  : self.sender_address,
            "receiver_address": self.receiver_address,
            "amount"          : self.amount,
            "timestamp"       : self.timestamp,
        }
        return hashlib.sha256(
            json.dumps(d, sort_keys=True).encode()
        ).hexdigest()

    # ── Signing ───────────────────────────────────────────────────────

    def sign(self, wallet: "Wallet") -> None:
        """
        Sign this transaction with the sender's wallet.

        Raises ValueError if the wallet address doesn't match the
        declared sender — you can't sign someone else's transaction.
        """
        if wallet.address != self.sender_address:
            raise ValueError(
                f"Wallet address {wallet.address!r} does not match "
                f"sender address {self.sender_address!r}"
            )
        self.sender_public_key = wallet.public_key_hex()
        self.signature         = wallet.sign(self._payload())

    # ── Verification ─────────────────────────────────────────────────

    def verify(self) -> bool:
        """
        Verify that:
          1. The transaction has a signature
          2. The public key hashes to the declared sender address
          3. The signature is valid for the payload

        Call this before including a tx in a block.
        """
        if not self.signature:
            return False

        # Re-derive the address from the embedded public key and compare.
        # This ensures the public key actually belongs to the declared sender.
        derived_address = public_key_to_address(
            bytes.fromhex(self.sender_public_key)
        )
        if derived_address != self.sender_address:
            return False

        return Wallet.verify(self._payload(), self.signature,
                             self.sender_public_key)

    # ── Serialisation ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "tx_id"            : self.tx_id,
            "sender_address"   : self.sender_address,
            "receiver_address" : self.receiver_address,
            "amount"           : self.amount,
            "timestamp"        : self.timestamp,
            "sender_public_key": self.sender_public_key,
            "signature"        : self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Transaction":
        tx = cls.__new__(cls)
        tx.tx_id             = d["tx_id"]
        tx.sender_address    = d["sender_address"]
        tx.receiver_address  = d["receiver_address"]
        tx.amount            = d["amount"]
        tx.timestamp         = d["timestamp"]
        tx.sender_public_key = d["sender_public_key"]
        tx.signature         = d["signature"]
        return tx

    def __repr__(self) -> str:
        status = "✓ signed" if self.signature else "✗ unsigned"
        return (
            f"Transaction(\n"
            f"  id       = {self.tx_id[:16]}…\n"
            f"  from     = {self.sender_address}\n"
            f"  to       = {self.receiver_address}\n"
            f"  amount   = {self.amount}\n"
            f"  status   = {status}\n"
            f")"
        )

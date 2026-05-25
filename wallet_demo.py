"""
wallet_demo.py — Full wallet + blockchain integration demo
"""

from wallet import Wallet, Transaction
from blockchain import TransactionBlockchain
import tempfile

SEP  = "═" * 62
SEP2 = "─" * 62


# ─────────────────────────────────────────────────────────────────────
#  1. Create wallets
# ─────────────────────────────────────────────────────────────────────

print(SEP)
print("  Step 1 — Key pair generation")
print(SEP)

alice = Wallet()
bob   = Wallet()
carol = Wallet()
miner = Wallet()

for name, w in [("Alice", alice), ("Bob", bob),
                ("Carol", carol), ("Miner", miner)]:
    print(f"\n  {name}")
    print(f"    address    : {w.address}")
    print(f"    public key : {w.public_key_hex()[:40]}…  ({len(w.public_key_hex())//2} bytes)")
    print(f"    private key: {'*' * 32}  [hidden]")


# ─────────────────────────────────────────────────────────────────────
#  2. Boot a transaction-aware blockchain (miner gets coinbase rewards)
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 2 — Boot blockchain (miner = Miner wallet)")
print(SEP)

chain = TransactionBlockchain(miner_address=miner.address, silent=False)

# Seed Alice by directly mining a coinbase-only block
print(f"\n  Seeding Alice with a coinbase block (miner reward → Alice for demo)…")
chain.miner_address = alice.address
chain.mine_pending()
chain.miner_address = miner.address

print(f"\n  Balances after seed:")
for name, w in [("Alice", alice), ("Bob", bob), ("Carol", carol), ("Miner", miner)]:
    print(f"    {name:6s}: {chain.balance_of(w.address):.2f} coins")


# ─────────────────────────────────────────────────────────────────────
#  3. Create and sign transactions
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 3 — Create + sign transactions")
print(SEP)

# Alice → Bob
tx1 = Transaction(
    sender_address   = alice.address,
    receiver_address = bob.address,
    amount           = 4.0,
    sender_public_key= alice.public_key_hex(),
)
tx1.sign(alice)
print(f"\n  tx1 (Alice → Bob, 4 coins)")
print(f"    tx_id     : {tx1.tx_id[:32]}…")
print(f"    signature : {tx1.signature[:40]}…")
print(f"    verify()  : {tx1.verify()}")

# Alice → Carol
tx2 = Transaction(
    sender_address   = alice.address,
    receiver_address = carol.address,
    amount           = 3.0,
    sender_public_key= alice.public_key_hex(),
)
tx2.sign(alice)
print(f"\n  tx2 (Alice → Carol, 3 coins)")
print(f"    tx_id     : {tx2.tx_id[:32]}…")
print(f"    verify()  : {tx2.verify()}")


# ─────────────────────────────────────────────────────────────────────
#  4. Submit to mempool
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 4 — Submit to mempool")
print(SEP + "\n")

chain.submit_transaction(tx1)
chain.submit_transaction(tx2)
print(f"\n  Mempool size: {chain.pending_count()} pending transaction(s)")


# ─────────────────────────────────────────────────────────────────────
#  5. Mine the pending transactions
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 5 — Mine block (includes pending txs + coinbase reward)")
print(SEP + "\n")

block = chain.mine_pending()
print(f"\n  Block #{block.index} mined  hash={block.hash[:20]}…")
print(f"  Mempool after mining: {chain.pending_count()} pending")


# ─────────────────────────────────────────────────────────────────────
#  6. Check balances
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 6 — Balances after mining")
print(SEP)

print()
for name, w in [("Alice", alice), ("Bob", bob), ("Carol", carol), ("Miner", miner)]:
    bal = chain.balance_of(w.address)
    print(f"    {name:6s}: {bal:.2f} coins")


# ─────────────────────────────────────────────────────────────────────
#  7. Bob spends his coins (now he has funds)
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 7 — Bob → Carol (Bob spends his received coins)")
print(SEP + "\n")

tx3 = Transaction(
    sender_address   = bob.address,
    receiver_address = carol.address,
    amount           = 2.0,
    sender_public_key= bob.public_key_hex(),
)
tx3.sign(bob)
chain.submit_transaction(tx3)
chain.mine_pending()

print(f"\n  Final balances:")
for name, w in [("Alice", alice), ("Bob", bob), ("Carol", carol), ("Miner", miner)]:
    bal = chain.balance_of(w.address)
    bar = "█" * int(bal)
    print(f"    {name:6s}: {bal:5.2f}  {bar}")


# ─────────────────────────────────────────────────────────────────────
#  8. Transaction history
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 8 — Alice's transaction history (from chain scan)")
print(SEP)

history = chain.transaction_history(alice.address)
for tx in history:
    direction = "→ sent" if tx["sender_address"] == alice.address else "← recv"
    other = (tx["receiver_address"] if tx["sender_address"] == alice.address
             else tx["sender_address"])
    print(f"  block #{tx['_block']}  {direction}  {tx['amount']:.2f} coins  "
          f"{'to' if direction.startswith('→') else 'from'} {other[:12]}…")


# ─────────────────────────────────────────────────────────────────────
#  9. ATTACK 1 — Tamper with amount after signing
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 9 — Attack: tamper with amount after signing")
print(SEP + "\n")

evil_tx = Transaction(
    sender_address   = alice.address,
    receiver_address = bob.address,
    amount           = 1.0,
    sender_public_key= alice.public_key_hex(),
)
evil_tx.sign(alice)
print(f"  Signed tx  amount=1.0   verify={evil_tx.verify()}")

# Attacker intercepts and changes the amount
evil_tx.amount = 9999.0
print(f"  Tampered  amount=9999  verify={evil_tx.verify()}  "
      f"← signature now invalid")

accepted = chain.submit_transaction(evil_tx)
print(f"  Mempool accepted: {accepted}  (correctly rejected)")


# ─────────────────────────────────────────────────────────────────────
#  10. ATTACK 2 — Sign with the wrong wallet
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 10 — Attack: Carol tries to spend Alice's coins")
print(SEP + "\n")

try:
    theft_tx = Transaction(
        sender_address   = alice.address,
        receiver_address = carol.address,
        amount           = 5.0,
        sender_public_key= carol.public_key_hex(),
    )
    theft_tx.sign(carol)
except ValueError as e:
    print(f"  sign() raised ValueError: {e}")

manual_theft = Transaction(
    sender_address   = alice.address,
    receiver_address = carol.address,
    amount           = 5.0,
    sender_public_key= carol.public_key_hex(),
)
manual_theft.signature = carol.sign(manual_theft._payload())
print(f"  Manual forgery verify(): {manual_theft.verify()}  "
      f"← pubkey→address mismatch detected")


# ─────────────────────────────────────────────────────────────────────
#  11. Save / load wallet
# ─────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("  Step 11 — Save and reload wallet from disk")
print(SEP + "\n")

save_path = tempfile.gettempdir() + "/alice_wallet.pem"
alice.save(save_path, password="s3cr3t")
alice2 = Wallet.load(save_path, password="s3cr3t")
print(f"  Saved  address: {alice.address}")
print(f"  Loaded address: {alice2.address}")
print(f"  Match:          {alice.address == alice2.address}  "
      f"← same key pair recovered from disk")

tx_test = Transaction(
    sender_address   = alice.address,
    receiver_address = bob.address,
    amount           = 0.5,
    sender_public_key= alice2.public_key_hex(),
)
tx_test.sign(alice2)
print(f"  Tx signed by reloaded key — verify(): {tx_test.verify()}")


print(f"\n{SEP}")
print("  Chain integrity check")
print(SEP)
print(f"  Blocks: {len(chain)}")
print(f"  Valid:  {chain.is_valid()}")
print(f"\n  All done.")
print(SEP)

"""wallet_test.py — Minimal tests for Wallet and Transaction
"""

from wallet import Wallet, Transaction
import tempfile


def run_tests():
    alice = Wallet()
    bob = Wallet()

    print("Created wallets:")
    print("  Alice:", alice.address)
    print("  Bob  :", bob.address)

    # Create a transaction alice -> bob
    tx = Transaction(sender_address=alice.address,
                     receiver_address=bob.address,
                     amount=1.23,
                     sender_public_key=alice.public_key_hex())
    tx.sign(alice)
    print("Signed tx, verify() ->", tx.verify())

    # Tamper with amount
    tx.amount = 9999.0
    print("After tamper, verify() ->", tx.verify())

    # Wrong signer
    tx2 = Transaction(sender_address=alice.address,
                      receiver_address=bob.address,
                      amount=0.5,
                      sender_public_key=bob.public_key_hex())
    tx2.signature = bob.sign(tx2._payload())
    print("Wrong-signer verify() ->", tx2.verify())

    # Save / load wallet
    path = tempfile.gettempdir() + "/alice_test.pem"
    alice.save(path, password="testpw")
    alice2 = Wallet.load(path, password="testpw")
    print("Saved/loaded address match ->", alice.address == alice2.address)


if __name__ == '__main__':
    run_tests()

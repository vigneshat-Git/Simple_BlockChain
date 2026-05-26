"""wallet_cli.py — Interactive wallet and transaction demo
"""

import os
import sys
import getpass
from typing import Dict, Optional

from wallet import Wallet, Transaction
from blockchain import TransactionBlockchain


def clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


def prompt_index(count: int, prompt: str) -> Optional[int]:
    if count == 0:
        return None
    while True:
        choice = input(prompt).strip()
        if choice == "":
            return None
        if choice.isdigit():
            idx = int(choice)
            if 0 <= idx < count:
                return idx
        print(f"Please enter a number from 0 to {count - 1}, or blank to cancel.")


def list_wallets(wallets: Dict[str, Wallet]) -> None:
    if not wallets:
        print("No wallets created yet.")
        return
    print("Wallets:")
    for idx, (name, wallet) in enumerate(wallets.items()):
        print(f"  [{idx}] {name}: {wallet.address}")


def choose_wallet(wallets: Dict[str, Wallet], prompt: str) -> Optional[str]:
    if not wallets:
        print("No wallets available.")
        return None
    list_wallets(wallets)
    idx = prompt_index(len(wallets), prompt)
    if idx is None:
        return None
    return list(wallets.keys())[idx]


def create_wallet(wallets: Dict[str, Wallet]) -> None:
    name = input("Enter a name for the new wallet: ").strip()
    if not name:
        print("Wallet creation cancelled.")
        return
    if name in wallets:
        print(f"A wallet named '{name}' already exists.")
        return
    wallet = Wallet()
    wallets[name] = wallet
    print(f"Created wallet '{name}' with address: {wallet.address}")


def save_wallet(wallets: Dict[str, Wallet]) -> None:
    name = choose_wallet(wallets, "Choose wallet index to save: ")
    if name is None:
        return
    wallet = wallets[name]
    path = input("Enter file path to save PEM (e.g. C:/temp/wallet.pem): ").strip()
    if not path:
        print("Save cancelled.")
        return
    password = getpass.getpass("Enter password to encrypt the wallet (blank = no password): ")
    try:
        wallet.save(path, password=password if password else None)
        print(f"Saved wallet '{name}' to {path}")
    except Exception as exc:
        print(f"Failed to save wallet: {exc}")


def load_wallet(wallets: Dict[str, Wallet]) -> None:
    path = input("Enter PEM path to load: ").strip()
    if not path:
        print("Load cancelled.")
        return
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        return
    password = getpass.getpass("Enter password if the PEM is encrypted (blank if none): ")
    try:
        wallet = Wallet.load(path, password=password if password else None)
    except Exception as exc:
        print(f"Failed to load wallet: {exc}")
        return
    name = input("Enter a name for the loaded wallet: ").strip()
    if not name:
        print("Load cancelled.")
        return
    if name in wallets:
        print(f"A wallet named '{name}' already exists.")
        return
    wallets[name] = wallet
    print(f"Loaded wallet '{name}' with address: {wallet.address}")


def show_balances(wallets: Dict[str, Wallet], chain: TransactionBlockchain) -> None:
    if not wallets:
        print("No wallets available.")
        return
    print("Balances:")
    for name, wallet in wallets.items():
        balance = chain.balance_of(wallet.address)
        print(f"  {name:10s}: {balance:.2f}")


def create_transaction(wallets: Dict[str, Wallet], chain: TransactionBlockchain) -> None:
    if len(wallets) < 2:
        print("Need at least two wallets to send a transaction.")
        return
    sender_name = choose_wallet(wallets, "Choose sender wallet index: ")
    if sender_name is None:
        return
    receiver_name = choose_wallet(wallets, "Choose receiver wallet index: ")
    if receiver_name is None:
        return
    if receiver_name == sender_name:
        print("Sender and receiver must be different wallets.")
        return
    sender = wallets[sender_name]
    receiver = wallets[receiver_name]
    try:
        amount = float(input("Enter amount to send: ").strip())
    except ValueError:
        print("Invalid amount.")
        return
    tx = Transaction(
        sender_address=sender.address,
        receiver_address=receiver.address,
        amount=amount,
        sender_public_key=sender.public_key_hex(),
    )
    try:
        tx.sign(sender)
    except ValueError as exc:
        print(f"Signing failed: {exc}")
        return
    success = chain.submit_transaction(tx)
    print("Transaction submitted." if success else "Transaction rejected.")


def choose_miner(wallets: Dict[str, Wallet], chain: TransactionBlockchain) -> None:
    name = choose_wallet(wallets, "Choose miner wallet index: ")
    if name is None:
        return
    chain.miner_address = wallets[name].address
    print(f"Miner wallet set to '{name}'. Rewards will go to {chain.miner_address}")


def show_history(wallets: Dict[str, Wallet], chain: TransactionBlockchain) -> None:
    name = choose_wallet(wallets, "Choose wallet index to view history: ")
    if name is None:
        return
    wallet = wallets[name]
    history = chain.transaction_history(wallet.address)
    if not history:
        print("No transactions found for this wallet.")
        return
    print(f"Transaction history for {name} ({wallet.address}):")
    for tx in history:
        direction = "sent" if tx["sender_address"] == wallet.address else "received"
        other = tx["receiver_address"] if direction == "sent" else tx["sender_address"]
        print(f"  block {tx['_block']}: {direction} {tx['amount']:.2f} {'to' if direction == 'sent' else 'from'} {other} (id={tx['tx_id'][:10]}…)")


def main() -> None:
    wallets: Dict[str, Wallet] = {}
    chain = TransactionBlockchain(miner_address="COINBASE", silent=False)
    miner_name: Optional[str] = None

    while True:
        print("\n=== Wallet CLI Demo ===")
        print("1) Create wallet")
        print("2) List wallets")
        print("3) Set miner wallet")
        print("4) Show balances")
        print("5) Create and submit transaction")
        print("6) Show pending transaction count")
        print("7) Mine pending transactions")
        print("8) Show wallet transaction history")
        print("9) Save wallet to PEM")
        print("10) Load wallet from PEM")
        print("0) Exit")
        choice = input("Choose an option: ").strip()

        if choice == "0":
            print("Goodbye.")
            break
        elif choice == "1":
            create_wallet(wallets)
        elif choice == "2":
            list_wallets(wallets)
        elif choice == "3":
            choose_miner(wallets, chain)
        elif choice == "4":
            show_balances(wallets, chain)
        elif choice == "5":
            create_transaction(wallets, chain)
        elif choice == "6":
            print(f"Pending tx count: {chain.pending_count()}")
        elif choice == "7":
            if chain.miner_address == "COINBASE":
                print("Miner address is not set. Set a miner wallet first.")
            else:
                chain.mine_pending()
        elif choice == "8":
            show_history(wallets, chain)
        elif choice == "9":
            save_wallet(wallets)
        elif choice == "10":
            load_wallet(wallets)
        else:
            print("Invalid selection. Please choose a number from the menu.")


if __name__ == "__main__":
    main()

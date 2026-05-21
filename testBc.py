from blockchain import Blockchain, P2PNode
import argparse
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single blockchain node.")
    parser.add_argument("--host", default="127.0.0.1", help="Host/IP to bind this node")
    parser.add_argument("--port", type=int, required=True, help="Port to bind this node")
    parser.add_argument(
        "--peer",
        action="append",
        default=[],
        help="Peer address to connect to, e.g. 192.168.1.11:6001. Can be repeated.",
    )
    args = parser.parse_args()

    bc = Blockchain()
    node = P2PNode(bc, host=args.host, port=args.port, peers=args.peer)
    node.start()

    time.sleep(1)
    print(f"Node started on {args.host}:{args.port}")
    print("Peers:", node.peers)

    try:
        while True:
            option = input(
                "1. Add block\n2. Show chain\n3. Show peers\nq. Quit\nOption: "
            ).strip().lower()

            if option == "1":
                data = input("Enter data for block: ").strip()
                new_block = bc.add_block(data)
                print(f"Added block #{new_block.index} with data: {new_block.data}")
            elif option == "2":
                for block in bc.chain:
                    print(
                        f"Block {block.index}: prev={block.prev_hash[:8]} hash={block.hash[:8]} data={block.data}"
                    )
            elif option == "3":
                print("Peers:", node.peers)
            elif option in {"q", "quit", "exit"}:
                break
            else:
                print("Invalid option. Choose 1, 2, 3, or q.")
    except KeyboardInterrupt:
        print("\nStopping node...")
    finally:
        node.stop()


if __name__ == "__main__":
    main()

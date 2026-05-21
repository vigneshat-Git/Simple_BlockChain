from blockchain import Blockchain, P2PNode
import time

bc_a = Blockchain()
node_a = P2PNode(bc_a, host='127.0.0.1', port=6000, peers=['127.0.0.1:6001'])
node_a.start()

bc_b = Blockchain()
node_b = P2PNode(bc_b, host='127.0.0.1', port=6001, peers=['127.0.0.1:6000'])
node_b.start()

time.sleep(1)
print('A peers', node_a.peers)
print('B peers', node_b.peers)
while True:
    option = input("1. Add block to A \n2. Add block to B\n3. Show chains\nOption: ")

    if option == '1':
        data = input("Enter data for block: ")
        new_block = bc_a.add_block(data)
        print(f"Added block #{new_block.index} to A with data: {new_block.data}")
    elif option == '2':
        data = input("Enter data for block: ")
        new_block = bc_b.add_block(data)
        print(f"Added block #{new_block.index} to B with data: {new_block.data}")
    #elif option == '3':
    #    show = input("1. Show chain A \n2. Show chain B\nOption: ")
    #    if show == '1':
    #        for block in bc_a.chain:
    #            print(f"Block {block.index}: {block.data}")
    #    else:
    #        for block in bc_b.chain:
    #            print(f"Block {block.index}: {block.data}")
    #else:
    #    print('Invalid option, please choose 1, 2, or 3.')
    elif option == '3':
        print("Peer A:")
        for block in bc_a.chain:
            print(f"Block {block.index}: {block.data}")
        print("\nPeer B:")
        for block in bc_b.chain:
            print(f"Block {block.index}: {block.data}")

node_a.stop()
node_b.stop()

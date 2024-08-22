import requests
import time
from ratelimit import limits, sleep_and_retry
from tqdm import tqdm

AVALANCHE_API_URL = "https://rpc.ankr.com/avalanche"  # Update this to Ankr's Avalanche endpoint
CALLS = 1800
RATE_LIMIT = 60  # 60 seconds (1 minute)
BATCH_SIZE = 1000  # We can increase this due to higher rate limit

print("Using Ankr API with optimized rate limits.")
time.sleep(2)  # Give the user time to read the message

session = requests.Session()
session.headers.update({'Content-Type': 'application/json'})

@sleep_and_retry
@limits(calls=CALLS, period=RATE_LIMIT)
def call_api(payload):
    for attempt in range(3):  # Try up to 3 times
        try:
            response = session.post(AVALANCHE_API_URL, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API call failed (attempt {attempt + 1}): {str(e)}")
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff

def get_latest_block_number():
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_blockNumber",
        "params": []
    }
    response = call_api(payload)
    if 'result' not in response:
        raise ValueError(f"Unexpected API response: {response}")
    return int(response['result'], 16)

def get_block_transactions_batch(block_numbers):
    payloads = [
        {
            "jsonrpc": "2.0",
            "id": i,
            "method": "eth_getBlockByNumber",
            "params": [hex(block_number), True]
        }
        for i, block_number in enumerate(block_numbers)
    ]
    response = call_api(payloads)
    transactions = []
    for r in response:
        if 'result' in r and r['result'] is not None:
            transactions.extend(r['result'].get('transactions', []))
    return transactions

def binary_search_first_transaction(address, start_block, end_block):
    print("Performing binary search to find the first transaction...")
    while start_block <= end_block:
        mid_block = (start_block + end_block) // 2
        print(f"Checking block range: {start_block} - {mid_block} - {end_block}")
        
        found_transaction = False
        for batch_start in range(start_block, mid_block + 1, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, mid_block + 1)
            print(f"Checking batch: {batch_start} - {batch_end}")
            try:
                batch_txs = get_block_transactions_batch(range(batch_start, batch_end))
                if any(tx['from'].lower() == address.lower() or (tx['to'] and tx['to'].lower() == address.lower()) for tx in batch_txs):
                    found_transaction = True
                    print(f"Found transaction in block range: {batch_start} - {batch_end}")
                    end_block = batch_end
                    break
            except Exception as e:
                print(f"Error checking batch {batch_start} - {batch_end}: {str(e)}")
        
        if not found_transaction:
            start_block = mid_block + 1
        
        print(f"Updated search range: {start_block} - {end_block}")
    
    # Fine-grained search in the final range
    for block in range(start_block, end_block + 1):
        print(f"Checking block: {block}")
        try:
            batch_txs = get_block_transactions_batch([block])
            for tx in batch_txs:
                if tx['from'].lower() == address.lower() or (tx['to'] and tx['to'].lower() == address.lower()):
                    print(f"Found first transaction in block: {block}")
                    return block
        except Exception as e:
            print(f"Error checking block {block}: {str(e)}")
    
    print("No transactions found")
    return None

def find_transactions_reverse_chronological(address, start_block, end_block, max_transactions=100):
    print(f"Searching for up to {max_transactions} transactions from block {end_block} to {start_block}...")
    transactions = []
    
    with tqdm(total=end_block-start_block, desc="Scanning blocks", unit="block") as pbar:
        while end_block >= start_block and len(transactions) < max_transactions:
            batch_start = max(end_block - BATCH_SIZE + 1, start_block)
            block_numbers = list(range(batch_start, end_block + 1))
            pbar.set_postfix_str(f"Current batch: {batch_start}-{end_block}")
            
            try:
                batch_txs = get_block_transactions_batch(block_numbers)
                relevant_txs = [tx for tx in batch_txs if tx['from'].lower() == address.lower() or (tx['to'] and tx['to'].lower() == address.lower())]
                transactions.extend(relevant_txs[:max_transactions - len(transactions)])
                
                if relevant_txs:
                    print(f"\nFound {len(relevant_txs)} transactions in blocks {batch_start}-{end_block}")
                
            except Exception as e:
                print(f"\nError processing batch {batch_start}-{end_block}: {str(e)}")
                time.sleep(1)  # Add a small delay before retrying
            
            pbar.update(end_block - batch_start + 1)
            end_block = batch_start - 1
    
    return transactions

def print_report(transactions, address, creation_block):
    if not transactions:
        print("No transactions found for this address.")
        return

    print(f"\nWallet created at block: {creation_block}")
    print(f"Total transactions found: {len(transactions)}")
    
    print("\nMost recent transactions:")
    for tx in transactions[:5]:  # Show only the 5 most recent transactions
        tx_type = "Sent" if tx['from'].lower() == address.lower() else "Received"
        print(f"  Type: {tx_type}")
        print(f"  Hash: {tx['hash']}")
        print(f"  From: {tx['from']}")
        print(f"  To: {tx['to']}")
        print(f"  Value: {int(tx['value'], 16) / 1e18:.4f} AVAX")
        print(f"  Block: {int(tx['blockNumber'], 16)}")
        print("  ---")

if __name__ == "__main__":
    address = "0xYourwalletaddress"  # Replace with your wallet address
    try:
        latest_block = get_latest_block_number()
        print(f"Latest block: {latest_block}")
        
        creation_block = binary_search_first_transaction(address, 0, latest_block)
        if creation_block:
            print(f"First transaction found in block {creation_block}")
            transactions = find_transactions_reverse_chronological(address, creation_block, latest_block)
            print_report(transactions, address, creation_block)
        else:
            print("No transactions found for this address.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
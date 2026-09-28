import argparse
import asyncio
import base64
import getpass
import math
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import batched
from typing import Final

from jito_py_rpc import JitoJsonRpcSDK
from solana.constants import LAMPORTS_PER_SOL
from solana.rpc.async_api import AsyncClient
from solana.rpc.models import TokenAccountOpts

from solders.solders import Pubkey, Keypair, Message
from solders.compute_budget import set_compute_unit_limit
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction

import spl.token.instructions as spl_token
from spl.token.models import CloseAccountParams

# Cluster	Public RPC endpoint	Description
# Mainnet	https://api.mainnet.solana.com	Production network using real SOL.
# Devnet	https://api.devnet.solana.com	Developer testing network. Use the Solana Faucet to get Devnet SOL.
# Testnet	https://api.testnet.solana.com	Validator testing network.

MAX_CLOSE_INSTRUCTIONS_PER_TRANSACTION: Final[int] = 20
COMPUTE_UNITS_PER_INSTRUCTION: Final[int] = 300
MIN_JITO_TIP: Final[int] = 1000
JITO_RPC_SDK:  Final[str] = 'https://mainnet.block-engine.jito.wtf/api/v1'
JITO_TRANSACTIONS_PER_BUNDLE: Final[int] = 5
SOLANA_RPC:  Final[str] = 'https://api.mainnet.solana.com'


def build_parser() -> argparse.ArgumentParser:
    """Construct the full argument parser."""
    parser = argparse.ArgumentParser(
        prog="solana-tools",
        description=(
            "SOLANA convenience tools for traders"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("show", help="Retrieve all zero balance accounts and report")
    sub.add_parser("close_accounts", help="Close all zero balance token accounts")

    return parser

@dataclass(frozen=True)
class TokenAccount:
    address: Pubkey
    lamports: int
    program_id: Pubkey


class TokenType(Enum):
    TOKEN_KEG  = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"),
    TOKEN_2022 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")

    def __init__(self, address):
        self.address = address

class ConsoleColors:

    def __init__(self):
        from _colorize import can_colorize, decolor, get_theme

        if can_colorize():
            self._theme = get_theme(force_color=True)
            self._decolor = lambda x: x
        else:
            self._theme = get_theme(force_no_color=True)
            self._decolor = decolor

    def title(self, text: str) -> str:
        return self._decolor(f"{self._theme.argparse.prog_extra}{text}{self._theme.argparse.reset}")


    def section(self, text: str) -> str:
        return self._decolor(f"{self._theme.argparse.summary_short_option}{text}{self._theme.argparse.reset}")

    def data(self, text: str) -> str:
        return self._decolor(f"{self._theme.argparse.summary_long_option}{text}{self._theme.argparse.reset}")

    def error(self, text: str) -> str:
        return self._decolor(f"{self._theme.traceback.error_highlight}{text}{self._theme.argparse.reset}")


async def get_min_transaction_fee( client: AsyncClient) -> int:
    # 1. Fetch the latest blockhash
    blockhash_resp = await client.get_latest_blockhash()
    recent_blockhash = blockhash_resp.value.blockhash

    # 2. Build a dummy transfer instruction to compile into a message
    from_wallet = Pubkey.new_unique()
    ix = transfer(TransferParams(
        from_pubkey=from_wallet,
        to_pubkey=Pubkey.new_unique(),
        lamports=1000
    ))

    # 3. Create the message layout
    message = Message.new_with_blockhash([ix], from_wallet, recent_blockhash)

    # 4. Fetch fee for this specific layout
    fee_resp = await client.get_fee_for_message(message)
    return fee_resp.value or 0


async def close_all_accounts() -> None:

    colors = ConsoleColors()
    private_key = Keypair.from_base58_string(getpass.getpass("Wallet private key: ", echo_char='*').strip())
    jito_client = JitoJsonRpcSDK(url=JITO_RPC_SDK)
    client = AsyncClient(SOLANA_RPC)

    accounts = await get_zero_balance_token_accounts(private_key.pubkey(), client)
    print(f"address: {private_key.pubkey()}")

    if len(accounts) == 0:
        print(colors.title("No accounts found"))
        return

    jito_tip_account = Pubkey.from_string(jito_client.get_random_tip_account())

    close_instructions = []

    for token_account in accounts:
        close_instructions.append( spl_token.close_account(
            CloseAccountParams(
                program_id= token_account.program_id,
                account= token_account.address,
                dest= private_key.pubkey(),
                owner= private_key.pubkey()
            ))
        )
    trx_ids = []
    processed_accounts = 0
    for instruction_set in batched(close_instructions, MAX_CLOSE_INSTRUCTIONS_PER_TRANSACTION):

        processed_accounts =+ len(instruction_set)
        base_instructions = [
            set_compute_unit_limit(COMPUTE_UNITS_PER_INSTRUCTION * ( len(instruction_set) + 2 )),
            # jito tip
            transfer(TransferParams(
                from_pubkey=private_key.pubkey(),
                to_pubkey=jito_tip_account,
                lamports=MIN_JITO_TIP
            ))
        ]

        recent_blockhash = await client.get_latest_blockhash()
        message = Message.new_with_blockhash(
            base_instructions + list(instruction_set) ,
            private_key.pubkey(),
            recent_blockhash.value.blockhash
        )
        transaction = Transaction.new_unsigned(message)
        transaction.sign([private_key], recent_blockhash.value.blockhash)

        result = jito_client.send_txn( params = base64.b64encode(bytes(transaction)).decode('ascii'), bundleOnly= False)

        if result['success']:
            trx_ids.append(result['data']['result'])
            print(f'\rAccounts Processed: {processed_accounts}/{len(close_instructions)}', end='')
        else:
            print(f"\nFailed to send transaction: {result.get('error', 'Unknown error')}")
        # JITO's limit, max transactions/second = 1
        await asyncio.sleep(1)

    print(f"\nTransaction IDs: {trx_ids}")
    await client.close()


async def show_wallet_status() -> None:
    wallet_int =  input("Wallet address: ").strip()
    if not wallet_int:
        print("Wallet address is not provided.")
        return

    client = AsyncClient(SOLANA_RPC)
    accounts = await get_zero_balance_token_accounts(Pubkey.from_string(wallet_int), client)

    lamports = 0

    min_processing_fee = await get_min_transaction_fee(client)


    for account in accounts:
        lamports += account.lamports


    cost  = math.ceil(math.ceil(len(accounts) / MAX_CLOSE_INSTRUCTIONS_PER_TRANSACTION)) * ( MIN_JITO_TIP + min_processing_fee )


    colors = ConsoleColors()
    print(colors.title("Balance information"))
    print(colors.section("    closable accounts:\t\t") + colors.data(f"{len(accounts)}"))
    print(colors.section("    recoverable SOL:\t\t") + colors.data(f"{lamports / LAMPORTS_PER_SOL}"))
    print(colors.section("    lamports:\t\t\t") + colors.data(f"{lamports}"))
    print(colors.section("    approximate close costs:\t") + colors.data(f"{cost / LAMPORTS_PER_SOL :.6f} SOL"))


async def get_zero_balance_token_accounts(wallet: Pubkey, client: AsyncClient) -> Sequence[TokenAccount]:


    if not await client.is_connected():
        raise Exception("Client is not connected")

    zero_balance_accounts = []

    for token_program in TokenType:
        token_accounts = await client.get_token_accounts_by_owner_json_parsed(
            owner = wallet,
            opts = TokenAccountOpts( program_id= token_program.address, encoding="jsonParsed" )
        )

        for account in token_accounts.value:
            if int(account.account.data.parsed['info']['tokenAmount']['uiAmount']) == 0:
                zero_balance_accounts.append(
                    TokenAccount(
                        address = account.pubkey,
                        lamports = account.account.lamports,
                        program_id= token_program.address))


    return zero_balance_accounts


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument list, defaulting to ``sys.argv[1:]``.

    Returns:
        A process exit code.
    """
    args = build_parser().parse_args(argv)


    try:
        match args.command:
            case "show":
                asyncio.run(show_wallet_status())
            case "close_accounts":
                asyncio.run(close_all_accounts())
    except Exception as e:
        # traceback.print_exc()
        print(ConsoleColors().error(e.__str__()))
        return 1
    return 0



if __name__ == "__main__":
    raise SystemExit(main())

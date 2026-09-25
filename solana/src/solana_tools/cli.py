import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from uuid import NIL

import math
from solana.constants import LAMPORTS_PER_SOL
from solana.rpc.async_api import AsyncClient
from solders.solders import Pubkey
from solana.rpc.models import MemcmpOpts, TokenAccountOpts
from typing import Final, Tuple

# Cluster	Public RPC endpoint	Description
# Mainnet	https://api.mainnet.solana.com	Production network using real SOL.
# Devnet	https://api.devnet.solana.com	Developer testing network. Use the Solana Faucet to get Devnet SOL.
# Testnet	https://api.testnet.solana.com	Validator testing network.

ACCOUNTS_PER_TRANSACTION: Final = 20
MIN_JITO_TIP: Final = 1000
JITO_RPC:  Final = 'https://mainnet.block-engine.jito.wtf'
JITO_TRANSACTIONS_PER_BUNDLE: Final = 5
SOLANA_RPC:  Final = 'https://api.mainnet.solana.com'


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
    sub.add_parser("close_accounts", help="Close all zero balance accounts")

    return parser

@dataclass(frozen=True)
class TokenAccount:
    address: Pubkey
    lamports: int
    type: TokenType


class TokenType(Enum):
    TOKEN_KEG  = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"),
    TOKEN_2022 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")

    def __init__(self, address):
        self.address = address

class ConsoleColors:

    def __init__(self):
        from _colorize import can_colorize, decolor, get_theme

        if can_colorize():
            self._theme = get_theme(force_color=True).argparse
            self._decolor = decolor
        else:
            self._theme = get_theme(force_no_color=True).argparse
            self._decolor = lambda x: x

    def title(self, text: str) -> str:
        return f"{self._theme.prog_extra}{text}{self._theme.reset}"


    def section(self, text: str) -> str:
        return f"{self._theme.summary_short_option}{text}{self._theme.reset}"

    def data(self, text: str) -> str:
        return f"{self._theme.summary_long_option}{text}{self._theme.reset}"






async def show_balance() -> None:
    wallet_int =  input("Wallet address: ").strip()
    if not wallet_int:
        print("Wallet address is not provided.")
        return

    client = AsyncClient(SOLANA_RPC)
    accounts = await get_zero_balance_token_accounts(Pubkey.from_string(wallet_int), client)

    lamports = 0

    for account in accounts:
        lamports += account.lamports


    cost  = ( math.ceil(math.ceil(len(accounts) / ACCOUNTS_PER_TRANSACTION) / JITO_TRANSACTIONS_PER_BUNDLE) * MIN_JITO_TIP)


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
                        type = token_program))


    return zero_balance_accounts


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument list, defaulting to ``sys.argv[1:]``.

    Returns:
        A process exit code.
    """
    args = build_parser().parse_args(argv)


    match args.command:
        case "show":
            asyncio.run(show_balance())



if __name__ == "__main__":
    raise SystemExit(main())

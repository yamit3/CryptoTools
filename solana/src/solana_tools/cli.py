import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import NIL

from solana.constants import LAMPORTS_PER_SOL
from solana.rpc.async_api import AsyncClient
from solders.solders import Pubkey
from solana.rpc.models import MemcmpOpts, TokenAccountOpts

# Cluster	Public RPC endpoint	Description
# Mainnet	https://api.mainnet.solana.com	Production network using real SOL.
# Devnet	https://api.devnet.solana.com	Developer testing network. Use the Solana Faucet to get Devnet SOL.
# Testnet	https://api.testnet.solana.com	Validator testing network.

TOKEN_2022_PROGRAM_ID = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
TOKEN_KEG_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")


@dataclass(frozen=True)
class TokenAccount:
    address: Pubkey
    lamports: int


async def show_balance() -> None:
    wallet_int =  input("Wallet address: ").strip()
    if not wallet_int:
        print("Wallet address is not provided.")
        return

    client = AsyncClient("https://api.mainnet.solana.com")
    accounts = await list_zero_balance_accounts(Pubkey.from_string(wallet_int), client)

    cont, lamports = 0, 0

    for account in accounts:
        lamports += account.lamports

    print(f"total zero token accounts: {cont}")
    print(f"sol: {lamports / LAMPORTS_PER_SOL}")
    print(f"lamports: {lamports}")


async def list_zero_balance_accounts(wallet: Pubkey, client: AsyncClient) -> Sequence[TokenAccount]:


    if not await client.is_connected():
        raise Exception("Client is not connected")

    zero_balance_accounts = []

    for token_program in [TOKEN_2022_PROGRAM_ID, TOKEN_KEG_PROGRAM_ID]:
        token_accounts = await client.get_token_accounts_by_owner_json_parsed(
            owner = wallet,
            opts = TokenAccountOpts( program_id=token_program, encoding="jsonParsed" )
        )

        for account in token_accounts.value:
            if int(account.account.data.parsed['info']['tokenAmount']['uiAmount']) == 0:
                zero_balance_accounts.append( TokenAccount(address = account.pubkey, lamports = account.account.lamports) )


    return zero_balance_accounts


def main() -> None:
    asyncio.run(show_balance())


if __name__ == "__main__":
    main()

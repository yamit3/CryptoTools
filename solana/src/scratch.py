import asyncio
from jito_py_rpc import JitoJsonRpcSDK


async def main():
    items = [1,2]
    print(items)

    batch_l1 =  chunk_it(  chunk_it(items, 20), 5)

    print(f"batch_l1: {batch_l1}")

    jito_client = JitoJsonRpcSDK(url="https://mainnet.block-engine.jito.wtf/api/v1")
    response = jito_client.get_inflight_bundle_statuses([''])



def chunk_it(lst: list, batch_size):
    def internal(list, batch_size):
        for i in range(0, len(list), batch_size):
            yield list[i:i + batch_size]
    return list(internal(lst, batch_size))

if __name__ == '__main__':
    asyncio.run(main())
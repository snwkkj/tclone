from telethon import TelegramClient


async def create_and_start_client(session_name, api_id, api_hash):
    client = TelegramClient(session_name, int(api_id), str(api_hash))
    await client.start()
    return client

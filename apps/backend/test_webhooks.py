import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def run():
    client = AsyncIOMotorClient("mongodb://localhost:27017/restobuzz")
    db = client.get_default_database()
    errors = await db.webhook_errors.find().to_list(10)
    print("Errors:", errors)
    messages = await db.outbound_messages.find().to_list(10)
    for m in messages:
        print(m.get('wa_message_id'), m.get('status'))

asyncio.run(run())

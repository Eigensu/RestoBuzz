"""Quick test: send felia_image template to a single number."""

import asyncio
from app.services.meta_api import send_template_message
from app.config import settings


async def main():
    wa_id, endpoint = await send_template_message(
        to="917977539750",
        template_name="felia_image",
        variables={},
        media_url="https://res.cloudinary.com/doyttqu8x/image/upload/v1774338751/whatsapp-media/xoygorfucrbeiws3c9o3.jpg",
    )
    print(f"Sent! wa_id={wa_id} endpoint={endpoint}")


asyncio.run(main())

import asyncio
import logging
from loguru import logger

from app.bot import dp, bot


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("ExcelBot v2 starting polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("ExcelBot v2 stopped.")


if __name__ == "__main__":
    asyncio.run(main())
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    engine = create_async_engine('postgresql+asyncpg://kubera:kubera_secret@localhost:5433/kubera')
    async with engine.begin() as conn:
        await conn.execute(text('ALTER TABLE company_users ADD COLUMN IF NOT EXISTS accessible_modules JSONB NOT NULL DEFAULT \'[]\'::jsonb;'))
    print('Done!')

if __name__ == '__main__':
    asyncio.run(main())

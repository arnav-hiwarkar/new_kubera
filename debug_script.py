import asyncio
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from app.models.auditor import Auditor
from app.models.company import Company, CompanyUser
from app.models.auditease import AuditEngagement, AuditorEngagementGrant

import logging
logging.basicConfig(level=logging.INFO)

DATABASE_URL = "sqlite+aiosqlite:///./kubera.db"
engine = create_async_engine(DATABASE_URL)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def check():
    async with async_session_maker() as session:
        grants = await session.execute(select(AuditorEngagementGrant))
        grants = grants.scalars().all()
        print(f"Total grants: {len(grants)}")
        for g in grants:
            print(f"Grant: {g.id}, Auditor: {g.auditor_id}, Engagement: {g.engagement_id}, Status: {g.status}")
            
        auditors = await session.execute(select(Auditor))
        for a in auditors.scalars().all():
            print(f"Auditor: {a.email}, ID: {a.id}")

asyncio.run(check())

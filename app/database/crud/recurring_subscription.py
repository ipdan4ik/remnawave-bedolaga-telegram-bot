"""CRUD operations for RecurringSubscription model."""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import RecurringSubscription, Subscription

logger = logging.getLogger(__name__)


async def get_recurring_subscription_by_subscription_id(
    db: AsyncSession,
    subscription_id: int,
) -> Optional[RecurringSubscription]:
    """Get recurring subscription by subscription ID."""
    result = await db.execute(
        select(RecurringSubscription)
        .options(selectinload(RecurringSubscription.subscription))
        .options(selectinload(RecurringSubscription.tariff))
        .where(RecurringSubscription.subscription_id == subscription_id)
    )
    return result.scalar_one_or_none()


async def get_recurring_subscription_by_cp_id(
    db: AsyncSession,
    cp_subscription_id: str,
) -> Optional[RecurringSubscription]:
    """Get recurring subscription by CloudPayments subscription ID."""
    result = await db.execute(
        select(RecurringSubscription)
        .options(selectinload(RecurringSubscription.subscription))
        .options(selectinload(RecurringSubscription.tariff))
        .where(RecurringSubscription.cloudpayments_subscription_id == cp_subscription_id)
    )
    return result.scalar_one_or_none()


async def get_recurring_subscription_by_user_id(
    db: AsyncSession,
    user_id: int,
) -> Optional[RecurringSubscription]:
    """Get recurring subscription by user ID."""
    # First get user's subscription
    subscription_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    subscription = subscription_result.scalar_one_or_none()
    
    if not subscription:
        return None
    
    return await get_recurring_subscription_by_subscription_id(db, subscription.id)


async def create_recurring_subscription(
    db: AsyncSession,
    subscription_id: int,
    cloudpayments_token: str,
    tariff_id: int,
    period_days: int,
    amount_kopeks: int,
    trial_period_days: int,
    trial_amount_kopeks: int,
    trial_start_date: datetime,
    trial_end_date: datetime,
    cloudpayments_subscription_id: Optional[str] = None,
    next_payment_date: Optional[datetime] = None,
    is_active: bool = True,
) -> RecurringSubscription:
    """Create a new recurring subscription."""
    recurring_sub = RecurringSubscription(
        subscription_id=subscription_id,
        cloudpayments_subscription_id=cloudpayments_subscription_id,
        cloudpayments_token=cloudpayments_token,
        tariff_id=tariff_id,
        period_days=period_days,
        amount_kopeks=amount_kopeks,
        trial_period_days=trial_period_days,
        trial_amount_kopeks=trial_amount_kopeks,
        trial_start_date=trial_start_date,
        trial_end_date=trial_end_date,
        is_active=is_active,
        next_payment_date=next_payment_date,
    )
    
    db.add(recurring_sub)
    await db.flush()
    await db.refresh(recurring_sub)
    
    logger.info(
        "Создана рекуррентная подписка: id=%s, subscription_id=%s, cp_subscription_id=%s",
        recurring_sub.id,
        subscription_id,
        cloudpayments_subscription_id,
    )
    
    return recurring_sub


async def update_recurring_subscription(
    db: AsyncSession,
    recurring_sub: RecurringSubscription,
    cloudpayments_subscription_id: Optional[str] = None,
    next_payment_date: Optional[datetime] = None,
    is_active: Optional[bool] = None,
    **kwargs,
) -> RecurringSubscription:
    """Update recurring subscription."""
    if cloudpayments_subscription_id is not None:
        recurring_sub.cloudpayments_subscription_id = cloudpayments_subscription_id
    if next_payment_date is not None:
        recurring_sub.next_payment_date = next_payment_date
    if is_active is not None:
        recurring_sub.is_active = is_active
    
    # Update any other fields from kwargs
    for key, value in kwargs.items():
        if hasattr(recurring_sub, key):
            setattr(recurring_sub, key, value)
    
    recurring_sub.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(recurring_sub)
    
    logger.info(
        "Обновлена рекуррентная подписка: id=%s, subscription_id=%s",
        recurring_sub.id,
        recurring_sub.subscription_id,
    )
    
    return recurring_sub


async def deactivate_recurring_subscription(
    db: AsyncSession,
    recurring_sub: RecurringSubscription,
) -> RecurringSubscription:
    """Deactivate recurring subscription."""
    recurring_sub.is_active = False
    recurring_sub.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(recurring_sub)
    
    logger.info(
        "Деактивирована рекуррентная подписка: id=%s, subscription_id=%s",
        recurring_sub.id,
        recurring_sub.subscription_id,
    )
    
    return recurring_sub

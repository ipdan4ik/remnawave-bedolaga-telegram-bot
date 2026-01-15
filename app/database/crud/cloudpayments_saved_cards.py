"""CRUD operations for CloudPayments saved cards."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CloudPaymentsSavedCard

logger = logging.getLogger(__name__)


async def create_saved_card(
    db: AsyncSession,
    *,
    user_id: int,
    token: str,
    card_first_six: Optional[str] = None,
    card_last_four: Optional[str] = None,
    card_type: Optional[str] = None,
    card_exp_date: Optional[str] = None,
    is_default: bool = False,
) -> CloudPaymentsSavedCard:
    """
    Create a new saved card record.

    Args:
        db: Database session
        user_id: User ID
        token: CloudPayments card token
        card_first_six: First 6 digits of card
        card_last_four: Last 4 digits of card
        card_type: Card type (Visa, MasterCard, etc.)
        card_exp_date: Card expiration date (MM/YY)
        is_default: Whether this is the default card

    Returns:
        Created CloudPaymentsSavedCard object
    """
    # If this is set as default, unset other default cards for this user
    if is_default:
        await db.execute(
            update(CloudPaymentsSavedCard)
            .where(CloudPaymentsSavedCard.user_id == user_id)
            .where(CloudPaymentsSavedCard.is_default == True)
            .values(is_default=False)
        )

    # Check if user has any cards - if not, make this one default
    result = await db.execute(
        select(CloudPaymentsSavedCard).where(CloudPaymentsSavedCard.user_id == user_id)
    )
    existing_cards = result.scalars().all()
    if not existing_cards:
        is_default = True

    card = CloudPaymentsSavedCard(
        user_id=user_id,
        token=token,
        card_first_six=card_first_six,
        card_last_four=card_last_four,
        card_type=card_type,
        card_exp_date=card_exp_date,
        is_default=is_default,
    )

    db.add(card)
    await db.flush()
    await db.refresh(card)

    logger.debug(
        "Created CloudPayments saved card: id=%s, user_id=%s, card_last_four=%s",
        card.id,
        user_id,
        card_last_four,
    )

    return card


async def get_user_saved_cards(
    db: AsyncSession,
    user_id: int,
) -> list[CloudPaymentsSavedCard]:
    """Get all saved cards for a user."""
    result = await db.execute(
        select(CloudPaymentsSavedCard)
        .where(CloudPaymentsSavedCard.user_id == user_id)
        .order_by(CloudPaymentsSavedCard.is_default.desc(), CloudPaymentsSavedCard.created_at.desc())
    )
    return list(result.scalars().all())


async def get_default_card(
    db: AsyncSession,
    user_id: int,
) -> Optional[CloudPaymentsSavedCard]:
    """Get default saved card for a user."""
    result = await db.execute(
        select(CloudPaymentsSavedCard).where(
            CloudPaymentsSavedCard.user_id == user_id,
            CloudPaymentsSavedCard.is_default == True,
        )
    )
    return result.scalars().first()


async def set_default_card(
    db: AsyncSession,
    card_id: int,
    user_id: int,
) -> Optional[CloudPaymentsSavedCard]:
    """Set a card as default for a user."""
    # Unset other default cards
    await db.execute(
        update(CloudPaymentsSavedCard)
        .where(CloudPaymentsSavedCard.user_id == user_id)
        .where(CloudPaymentsSavedCard.is_default == True)
        .values(is_default=False)
    )

    # Set this card as default
    await db.execute(
        update(CloudPaymentsSavedCard)
        .where(CloudPaymentsSavedCard.id == card_id)
        .where(CloudPaymentsSavedCard.user_id == user_id)
        .values(is_default=True)
    )

    await db.flush()

    result = await db.execute(
        select(CloudPaymentsSavedCard).where(CloudPaymentsSavedCard.id == card_id)
    )
    return result.scalars().first()


async def delete_saved_card(
    db: AsyncSession,
    card_id: int,
    user_id: int,
) -> bool:
    """Delete a saved card."""
    result = await db.execute(
        select(CloudPaymentsSavedCard).where(
            CloudPaymentsSavedCard.id == card_id,
            CloudPaymentsSavedCard.user_id == user_id,
        )
    )
    card = result.scalars().first()

    if not card:
        return False

    await db.delete(card)
    await db.flush()

    logger.info("Deleted CloudPayments saved card: id=%s, user_id=%s", card_id, user_id)
    return True


async def update_last_used(
    db: AsyncSession,
    card_id: int,
) -> Optional[CloudPaymentsSavedCard]:
    """Update last_used_at timestamp for a card."""
    await db.execute(
        update(CloudPaymentsSavedCard)
        .where(CloudPaymentsSavedCard.id == card_id)
        .values(last_used_at=datetime.utcnow(), updated_at=datetime.utcnow())
    )

    await db.flush()

    result = await db.execute(
        select(CloudPaymentsSavedCard).where(CloudPaymentsSavedCard.id == card_id)
    )
    return result.scalars().first()


async def get_card_by_token(
    db: AsyncSession,
    user_id: int,
    token: str,
) -> Optional[CloudPaymentsSavedCard]:
    """Get a saved card by token for a user."""
    result = await db.execute(
        select(CloudPaymentsSavedCard).where(
            CloudPaymentsSavedCard.user_id == user_id,
            CloudPaymentsSavedCard.token == token,
        )
    )
    return result.scalars().first()

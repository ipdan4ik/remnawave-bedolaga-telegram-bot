"""Service for CloudPayments recurrent payments."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import PaymentMethod, TransactionType
from app.services.cloudpayments_service import CloudPaymentsAPIError, CloudPaymentsService

logger = logging.getLogger(__name__)


class CloudPaymentsRecurrentService:
    """Service for handling recurrent payments via CloudPayments saved cards."""

    def __init__(self):
        self.cloudpayments_service = CloudPaymentsService()

    async def charge_subscription_renewal(
        self,
        db: AsyncSession,
        user: Any,
        subscription: Any,
        amount_kopeks: int,
        period_days: int,
        saved_card: Any,
    ) -> tuple[bool, Optional[str]]:
        """
        Charge subscription renewal using saved card token.

        Args:
            db: Database session
            user: User object
            subscription: Subscription object
            amount_kopeks: Amount to charge in kopeks
            period_days: Period in days for renewal
            saved_card: CloudPaymentsSavedCard object

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if not settings.ENABLE_CLOUDPAYMENTS_RECURRENT:
            return False, "Recurrent payments are disabled"

        if not saved_card or not saved_card.token:
            return False, "No saved card token available"

        # Period is already determined in monitoring_service, use it as-is
        # This parameter comes from the caller which handles tariff logic

        # Generate invoice ID
        invoice_id = self.cloudpayments_service.generate_invoice_id(user.telegram_id)

        description = f"Автопродление подписки на {period_days} дней"

        try:
            # Charge payment via CloudPayments API
            api_response = await self.cloudpayments_service.charge_by_token(
                token=saved_card.token,
                amount_kopeks=amount_kopeks,
                account_id=str(user.telegram_id),
                invoice_id=invoice_id,
                description=description,
            )

            # Check if payment was successful
            if not api_response.get("Success", False):
                error_message = api_response.get("Message", "Unknown error")
                reason_code = api_response.get("ReasonCode")
                
                # Map error codes to user-friendly messages
                user_message = error_message
                if reason_code == 5:
                    user_message = "Недостаточно средств на карте"
                elif reason_code == 6:
                    user_message = "Карта заблокирована"
                elif reason_code == 7:
                    user_message = "Истек срок действия карты"
                elif reason_code == 8:
                    user_message = "Токен карты недействителен"
                
                logger.error(
                    "CloudPayments recurrent payment failed: invoice=%s, reason=%s (code=%s)",
                    invoice_id,
                    error_message,
                    reason_code,
                )
                return False, user_message

            # Get transaction ID from response
            model = api_response.get("Model", {})
            transaction_id_cp = model.get("TransactionId")

            # Create payment record
            from app.database.crud.cloudpayments import create_cloudpayments_payment

            payment = await create_cloudpayments_payment(
                db=db,
                user_id=user.id,
                invoice_id=invoice_id,
                amount_kopeks=amount_kopeks,
                description=description,
                currency="RUB",
                test_mode=settings.CLOUDPAYMENTS_TEST_MODE,
            )

            if not payment:
                logger.error("Не удалось создать запись платежа для рекуррентного списания")
                return False, "Failed to create payment record"

            # Update payment record
            payment.transaction_id_cp = transaction_id_cp
            payment.status = "completed"
            payment.is_paid = True
            payment.paid_at = datetime.utcnow()
            payment.token = saved_card.token
            payment.card_first_six = saved_card.card_first_six
            payment.card_last_four = saved_card.card_last_four
            payment.card_type = saved_card.card_type
            payment.card_exp_date = saved_card.card_exp_date
            payment.test_mode = settings.CLOUDPAYMENTS_TEST_MODE
            payment.callback_payload = api_response

            await db.flush()

            # Create transaction record
            from app.database.crud.transaction import create_transaction

            transaction = await create_transaction(
                db=db,
                user_id=user.id,
                type=TransactionType.SUBSCRIPTION_PAYMENT,
                amount_kopeks=amount_kopeks,
                description=description,
                payment_method=PaymentMethod.CLOUDPAYMENTS,
                external_id=str(transaction_id_cp) if transaction_id_cp else invoice_id,
                is_completed=True,
            )

            payment.transaction_id = transaction.id

            # Update last_used_at for saved card
            from app.database.crud.cloudpayments_saved_cards import update_last_used

            await update_last_used(db, saved_card.id)

            await db.commit()

            logger.info(
                "CloudPayments рекуррентный платёж успешно обработан: invoice=%s, amount=%s₽, user=%s, period=%s дней",
                invoice_id,
                amount_kopeks / 100,
                user.telegram_id,
                period_days,
            )

            return True, None

        except CloudPaymentsAPIError as error:
            error_message = str(error)
            reason_code = getattr(error, "reason_code", None)
            
            # Map error codes to user-friendly messages
            user_message = error_message
            if reason_code == 5:
                user_message = "Недостаточно средств на карте"
            elif reason_code == 6:
                user_message = "Карта заблокирована"
            elif reason_code == 7:
                user_message = "Истек срок действия карты"
            elif reason_code == 8:
                user_message = "Токен карты недействителен"
            
            logger.error(
                "CloudPayments API error при рекуррентном списании: invoice=%s, error=%s, code=%s",
                invoice_id,
                error_message,
                reason_code,
            )
            return False, user_message

        except Exception as error:
            logger.exception(
                "Непредвиденная ошибка при рекуррентном списании CloudPayments: invoice=%s, error=%s",
                invoice_id,
                error,
            )
            return False, str(error)

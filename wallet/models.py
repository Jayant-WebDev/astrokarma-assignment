from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction



# Create your models here.
class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet',
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    def has_minimum_to_start(self, per_minute_cost):
        """Assignment rule: need at least 5 × per-minute cost to start."""
        required = Decimal(per_minute_cost) * 5
        return self.balance >= required
    def can_debit(self, amount):
        """True if balance can cover this amount without going negative."""
        amount = Decimal(amount)
        return amount > 0 and self.balance >= amount
    def debit(self, amount):
        """
        Subtract amount from balance.
        Raises ValidationError if amount is invalid or balance is insufficient.
        """
        amount = Decimal(amount)
        if amount <= 0:
            raise ValidationError('Debit amount must be positive.')
        with transaction.atomic():
            # lock this row so two billings can't race
            wallet = Wallet.objects.select_for_update().get(pk=self.pk)
            if wallet.balance < amount:
                raise ValidationError('Insufficient wallet balance.')
            wallet.balance -= amount
            wallet.save(update_fields=['balance'])
            self.balance = wallet.balance
        return self.balance
    
class RechargeTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=64, unique=True)  # unique → idempotency key
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)  # useful, not strictly required
from django.conf import settings
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        USER = 'user', 'User'
        PROVIDER = 'provider', 'Provider'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.USER,
    )

    def __str__(self):
        return f'{self.user.username} ({self.role})'

    @property
    def is_provider(self):
        return self.role == self.Role.PROVIDER

    @property
    def is_user(self):
        return self.role == self.Role.USER


class ConsultationSession(models.Model):
    """
    Paid 1:1 consultation with a wallet-billed lifecycle.
    States: unassigned → assigned → accepted_by_provider → in_progress → completed
    """

    class Status(models.TextChoices):
        UNASSIGNED = 'unassigned', 'Unassigned'
        ASSIGNED = 'assigned', 'Assigned'
        ACCEPTED_BY_PROVIDER = 'accepted_by_provider', 'Accepted by provider'
        IN_PROGRESS = 'in_progress', 'In progress'
        COMPLETED = 'completed', 'Completed'

    class EndedBy(models.TextChoices):
        USER = 'user', 'User'
        PROVIDER = 'provider', 'Provider'
        SYSTEM = 'system', 'System'

    # Who is in the session
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='consultation_sessions_as_user',
    )
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consultation_sessions_as_provider',
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.UNASSIGNED,
    )

    # Billing — cost is fixed once the session starts (assignment rule)
    per_minute_cost = models.DecimalField(max_digits=10, decimal_places=2)
    minutes_billed = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    ended_by = models.CharField(
        max_length=20,
        choices=EndedBy.choices,
        null=True,
        blank=True,
    )
    end_reason = models.CharField(max_length=255, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f'Session {self.pk} ({self.status})'
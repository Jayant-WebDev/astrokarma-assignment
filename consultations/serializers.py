from rest_framework import serializers

from .models import ConsultationSession


class ConsultationSessionSerializer(serializers.ModelSerializer):
    """Read/list a session."""

    class Meta:
        model = ConsultationSession
        fields = [
            'id',
            'user',
            'provider',
            'status',
            'per_minute_cost',
            'minutes_billed',
            'started_at',
            'ended_at',
            'ended_by',
            'end_reason',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class CreateSessionSerializer(serializers.Serializer):
    """USER creates a session (starts as unassigned)."""

    per_minute_cost = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_per_minute_cost(self, value):
        if value <= 0:
            raise serializers.ValidationError('per_minute_cost must be positive.')
        return value


class AssignSessionSerializer(serializers.Serializer):
    """Assign a provider to an unassigned session."""

    provider_id = serializers.IntegerField()


class BillSessionSerializer(serializers.Serializer):
    """
    Bill N minutes for an in_progress session.
    Default 1 minute; used by periodic billing.
    """

    minutes = serializers.IntegerField(min_value=1, default=1)
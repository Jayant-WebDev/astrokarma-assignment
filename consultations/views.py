from django.shortcuts import render

# Create your views here.
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from wallet.models import Wallet

from .models import ConsultationSession, Profile
from .serializers import (
    AssignSessionSerializer,
    BillSessionSerializer,
    ConsultationSessionSerializer,
    CreateSessionSerializer,
)
from .transitions import assert_can_transition

User = get_user_model()
Status = ConsultationSession.Status
EndedBy = ConsultationSession.EndedBy


def _bad_transition(exc):
    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class CreateSessionView(APIView):
    """USER creates a session → status=unassigned."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = ConsultationSession.objects.create(
            user=request.user,
            per_minute_cost=serializer.validated_data['per_minute_cost'],
            status=Status.UNASSIGNED,
        )
        return Response(
            ConsultationSessionSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )


class AssignSessionView(APIView):
    """unassigned → assigned (attach provider)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        serializer = AssignSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = get_object_or_404(ConsultationSession, pk=pk)
        try:
            assert_can_transition(session.status, Status.ASSIGNED)
        except ValueError as exc:
            return _bad_transition(exc)

        provider = get_object_or_404(User, pk=serializer.validated_data['provider_id'])
        profile = getattr(provider, 'profile', None)
        if profile is None or not profile.is_provider:
            return Response(
                {'detail': 'provider_id must belong to a PROVIDER.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.provider = provider
        session.status = Status.ASSIGNED
        session.save(update_fields=['provider', 'status', 'updated_at'])
        return Response(ConsultationSessionSerializer(session).data)


class AcceptSessionView(APIView):
    """assigned → accepted_by_provider (provider only)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        session = get_object_or_404(ConsultationSession, pk=pk)
        try:
            assert_can_transition(session.status, Status.ACCEPTED_BY_PROVIDER)
        except ValueError as exc:
            return _bad_transition(exc)

        if session.provider_id != request.user.id:
            return Response(
                {'detail': 'Only the assigned provider can accept.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        session.status = Status.ACCEPTED_BY_PROVIDER
        session.save(update_fields=['status', 'updated_at'])
        return Response(ConsultationSessionSerializer(session).data)


class StartSessionView(APIView):
    """accepted_by_provider → in_progress (user only; min 5× cost)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        session = get_object_or_404(ConsultationSession, pk=pk)
        try:
            assert_can_transition(session.status, Status.IN_PROGRESS)
        except ValueError as exc:
            return _bad_transition(exc)

        if session.user_id != request.user.id:
            return Response(
                {'detail': 'Only the session user can start.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # One active (in_progress) session per user
        if ConsultationSession.objects.filter(
            user=request.user,
            status=Status.IN_PROGRESS,
        ).exists():
            return Response(
                {'detail': 'User already has an in_progress session.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        if not wallet.has_minimum_to_start(session.per_minute_cost):
            return Response(
                {
                    'detail': (
                        'Insufficient balance to start. '
                        'Need at least 5 × per_minute_cost.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.status = Status.IN_PROGRESS
        session.started_at = timezone.now()
        session.save(update_fields=['status', 'started_at', 'updated_at'])
        return Response(ConsultationSessionSerializer(session).data)


class EndSessionView(APIView):
    """in_progress → completed (user or provider)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        session = get_object_or_404(ConsultationSession, pk=pk)
        try:
            assert_can_transition(session.status, Status.COMPLETED)
        except ValueError as exc:
            return _bad_transition(exc)

        is_user = session.user_id == request.user.id
        is_provider = session.provider_id == request.user.id
        if not (is_user or is_provider):
            return Response(
                {'detail': 'Only session user or provider can end.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        session.status = Status.COMPLETED
        session.ended_at = timezone.now()
        session.ended_by = EndedBy.USER if is_user else EndedBy.PROVIDER
        session.end_reason = ''
        session.save(
            update_fields=['status', 'ended_at', 'ended_by', 'end_reason', 'updated_at']
        )
        return Response(ConsultationSessionSerializer(session).data)


class BillSessionView(APIView):
    """
    Bill an in_progress session.
    Body: {"minutes": N} means "ensure total minutes_billed >= N" (idempotent).
    If wallet cannot cover the next minute → system ends session.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        serializer = BillSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_minutes = serializer.validated_data['minutes']

        session = get_object_or_404(ConsultationSession, pk=pk)
        if session.status != Status.IN_PROGRESS:
            return Response(
                {'detail': 'Can only bill an in_progress session.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wallet, _ = Wallet.objects.get_or_create(user=session.user)

        with transaction.atomic():
            session = (
                ConsultationSession.objects.select_for_update().get(pk=session.pk)
            )
            # Re-check inside lock
            if session.status != Status.IN_PROGRESS:
                return Response(
                    {'detail': 'Can only bill an in_progress session.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Already billed up to target → no double charge
            while session.minutes_billed < target_minutes:
                if not wallet.can_debit(session.per_minute_cost):
                    session.status = Status.COMPLETED
                    session.ended_at = timezone.now()
                    session.ended_by = EndedBy.SYSTEM
                    session.end_reason = 'Insufficient Balance'
                    session.save(
                        update_fields=[
                            'status',
                            'ended_at',
                            'ended_by',
                            'end_reason',
                            'updated_at',
                        ]
                    )
                    break

                try:
                    wallet.debit(session.per_minute_cost)
                except ValidationError as exc:
                    session.status = Status.COMPLETED
                    session.ended_at = timezone.now()
                    session.ended_by = EndedBy.SYSTEM
                    session.end_reason = 'Insufficient Balance'
                    session.save(
                        update_fields=[
                            'status',
                            'ended_at',
                            'ended_by',
                            'end_reason',
                            'updated_at',
                        ]
                    )
                    break

                session.minutes_billed += 1
                session.save(update_fields=['minutes_billed', 'updated_at'])

        session.refresh_from_db()
        wallet.refresh_from_db()
        return Response(
            {
                'session': ConsultationSessionSerializer(session).data,
                'wallet_balance': str(wallet.balance),
            }
        )
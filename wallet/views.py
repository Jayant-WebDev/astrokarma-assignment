import uuid
from rest_framework.views import APIView
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import Wallet, RechargeTransaction
from .serializers import WalletSerializer, RechargeInitiateSerializer, RechargeCallbackSerializer


class WalletBalanceView(APIView):
    """Return the logged-in user's wallet balance."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # One wallet per user; create with 0 if it doesn't exist yet
        wallet, _created = Wallet.objects.get_or_create(user=request.user)
        serializer = WalletSerializer(wallet)
        return Response(serializer.data)


class RechargeInitiateView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = RechargeInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        txn = RechargeTransaction.objects.create(
            user=request.user,
            amount=serializer.validated_data['amount'],
            reference=str(uuid.uuid4()),
            status=RechargeTransaction.Status.PENDING,
        )
        return Response(
            {
                'reference': txn.reference,
                'amount': str(txn.amount),
                'status': txn.status,
            },
            status=status.HTTP_201_CREATED,
        )

class RechargeCallbackView(APIView):
    """
    Mock payment webhook.
    Credits the wallet only once for a successful reference.
    """
    permission_classes = [AllowAny]  # mock webhook; OK for assignment/tests
    def post(self, request):
        serializer = RechargeCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reference = serializer.validated_data['reference']
        callback_status = serializer.validated_data['status']
        txn = get_object_or_404(RechargeTransaction, reference=reference)
        # Already succeeded → idempotent: do not credit again
        if txn.status == RechargeTransaction.Status.SUCCESS:
            wallet, _ = Wallet.objects.get_or_create(user=txn.user)
            return Response(
                {
                    'reference': txn.reference,
                    'status': txn.status,
                    'balance': str(wallet.balance),
                    'detail': 'Already processed',
                }
            )
        if callback_status == 'failed':
            txn.status = RechargeTransaction.Status.FAILED
            txn.save(update_fields=['status'])
            return Response(
                {
                    'reference': txn.reference,
                    'status': txn.status,
                }
            )
        # First successful callback → credit once
        with transaction.atomic():
            txn.status = RechargeTransaction.Status.SUCCESS
            txn.save(update_fields=['status'])
            wallet, _ = Wallet.objects.get_or_create(user=txn.user)
            wallet.balance += txn.amount
            wallet.save(update_fields=['balance'])
        return Response(
            {
                'reference': txn.reference,
                'status': txn.status,
                'balance': str(wallet.balance),
            }
        )

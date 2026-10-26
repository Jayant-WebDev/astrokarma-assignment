from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from consultations.models import ConsultationSession, Profile
from wallet.models import Wallet

User = get_user_model()


class AssignmentScenarioTests(APITestCase):
    """Required test scenarios from the assignment PDF (§6)."""

    def setUp(self):
        self.customer = User.objects.create_user(
            username='customer',
            password='pass12345',
        )
        self.provider = User.objects.create_user(
            username='provider',
            password='pass12345',
        )
        # Signal creates Profile with role=user; promote provider.
        self.provider.profile.role = Profile.Role.PROVIDER
        self.provider.profile.save(update_fields=['role'])

        self.cost = Decimal('50.00')

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _recharge(self, user, amount):
        """Mock recharge: initiate + successful callback."""
        self._auth(user)
        initiate = self.client.post(
            '/api/wallet/recharge/',
            {'amount': str(amount)},
            format='json',
        )
        self.assertEqual(initiate.status_code, status.HTTP_201_CREATED)
        reference = initiate.data['reference']

        callback = self.client.post(
            '/api/wallet/recharge/callback/',
            {'reference': reference, 'status': 'success'},
            format='json',
        )
        self.assertEqual(callback.status_code, status.HTTP_200_OK)
        return reference

    def _create_session_through_accept(self):
        """Create → assign → accept. Leaves status=accepted_by_provider."""
        self._auth(self.customer)
        create = self.client.post(
            '/api/sessions/',
            {'per_minute_cost': str(self.cost)},
            format='json',
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        session_id = create.data['id']

        assign = self.client.post(
            f'/api/sessions/{session_id}/assign/',
            {'provider_id': self.provider.id},
            format='json',
        )
        self.assertEqual(assign.status_code, status.HTTP_200_OK)

        self._auth(self.provider)
        accept = self.client.post(f'/api/sessions/{session_id}/accept/')
        self.assertEqual(accept.status_code, status.HTTP_200_OK)
        return session_id

    def test_1_insufficient_balance_cannot_start(self):
        """User with less than 5× per-minute cost cannot start."""
        # Need 250 to start; give only 200.
        self._recharge(self.customer, Decimal('200.00'))
        session_id = self._create_session_through_accept()

        self._auth(self.customer)
        start = self.client.post(f'/api/sessions/{session_id}/start/')
        self.assertEqual(start.status_code, status.HTTP_400_BAD_REQUEST)

        session = ConsultationSession.objects.get(pk=session_id)
        self.assertEqual(
            session.status,
            ConsultationSession.Status.ACCEPTED_BY_PROVIDER,
        )

    def test_2_happy_path_wallet_debited_for_two_minutes(self):
        """Recharge → create → accept → start → bill 2 min → end."""
        self._recharge(self.customer, Decimal('500.00'))
        session_id = self._create_session_through_accept()

        self._auth(self.customer)
        start = self.client.post(f'/api/sessions/{session_id}/start/')
        self.assertEqual(start.status_code, status.HTTP_200_OK)
        self.assertEqual(start.data['status'], 'in_progress')

        bill = self.client.post(
            f'/api/sessions/{session_id}/bill/',
            {'minutes': 2},
            format='json',
        )
        self.assertEqual(bill.status_code, status.HTTP_200_OK)
        self.assertEqual(bill.data['session']['minutes_billed'], 2)

        end = self.client.post(f'/api/sessions/{session_id}/end/')
        self.assertEqual(end.status_code, status.HTTP_200_OK)
        self.assertEqual(end.data['status'], 'completed')
        self.assertEqual(end.data['ended_by'], 'user')

        wallet = Wallet.objects.get(user=self.customer)
        # 500 - (2 × 50) = 400
        self.assertEqual(wallet.balance, Decimal('400.00'))

    def test_3_balance_runs_out_system_ends_session(self):
        """During billing, insufficient next minute → system ends; no negative."""
        # Exactly 5 minutes of balance: can start, fifth minute empties wallet.
        self._recharge(self.customer, Decimal('250.00'))
        session_id = self._create_session_through_accept()

        self._auth(self.customer)
        start = self.client.post(f'/api/sessions/{session_id}/start/')
        self.assertEqual(start.status_code, status.HTTP_200_OK)

        # Ask for 6 minutes; after 5, next minute cannot be paid.
        bill = self.client.post(
            f'/api/sessions/{session_id}/bill/',
            {'minutes': 6},
            format='json',
        )
        self.assertEqual(bill.status_code, status.HTTP_200_OK)

        session = ConsultationSession.objects.get(pk=session_id)
        wallet = Wallet.objects.get(user=self.customer)

        self.assertEqual(session.status, ConsultationSession.Status.COMPLETED)
        self.assertEqual(session.ended_by, ConsultationSession.EndedBy.SYSTEM)
        self.assertEqual(session.end_reason, 'Insufficient Balance')
        self.assertEqual(session.minutes_billed, 5)
        self.assertEqual(wallet.balance, Decimal('0.00'))
        self.assertGreaterEqual(wallet.balance, Decimal('0.00'))

    def test_4_invalid_state_transition_returns_400(self):
        """Ending before start is invalid → HTTP 400."""
        self._auth(self.customer)
        create = self.client.post(
            '/api/sessions/',
            {'per_minute_cost': str(self.cost)},
            format='json',
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        session_id = create.data['id']

        end = self.client.post(f'/api/sessions/{session_id}/end/')
        self.assertEqual(end.status_code, status.HTTP_400_BAD_REQUEST)

        session = ConsultationSession.objects.get(pk=session_id)
        self.assertEqual(session.status, ConsultationSession.Status.UNASSIGNED)

    def test_5_duplicate_recharge_callback_credits_once(self):
        """Same successful callback twice → wallet credited only once."""
        self._auth(self.customer)
        initiate = self.client.post(
            '/api/wallet/recharge/',
            {'amount': '100.00'},
            format='json',
        )
        self.assertEqual(initiate.status_code, status.HTTP_201_CREATED)
        reference = initiate.data['reference']

        first = self.client.post(
            '/api/wallet/recharge/callback/',
            {'reference': reference, 'status': 'success'},
            format='json',
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self.client.post(
            '/api/wallet/recharge/callback/',
            {'reference': reference, 'status': 'success'},
            format='json',
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)

        wallet = Wallet.objects.get(user=self.customer)
        self.assertEqual(wallet.balance, Decimal('100.00'))

    def test_6_duplicate_billing_same_minutes_not_charged_twice(self):
        """Billing the same target minutes twice does not double-charge."""
        self._recharge(self.customer, Decimal('500.00'))
        session_id = self._create_session_through_accept()

        self._auth(self.customer)
        start = self.client.post(f'/api/sessions/{session_id}/start/')
        self.assertEqual(start.status_code, status.HTTP_200_OK)

        bill1 = self.client.post(
            f'/api/sessions/{session_id}/bill/',
            {'minutes': 2},
            format='json',
        )
        self.assertEqual(bill1.status_code, status.HTTP_200_OK)
        self.assertEqual(bill1.data['session']['minutes_billed'], 2)

        bill2 = self.client.post(
            f'/api/sessions/{session_id}/bill/',
            {'minutes': 2},
            format='json',
        )
        self.assertEqual(bill2.status_code, status.HTTP_200_OK)
        self.assertEqual(bill2.data['session']['minutes_billed'], 2)

        wallet = Wallet.objects.get(user=self.customer)
        # Only one round of 2 × 50 = 100 debited
        self.assertEqual(wallet.balance, Decimal('400.00'))

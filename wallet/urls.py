from django.urls import path
from .views import WalletBalanceView, RechargeInitiateView, RechargeCallbackView

urlpatterns = [
    path('wallet/', WalletBalanceView.as_view(), name='wallet-balance'),
    path('wallet/recharge/', RechargeInitiateView.as_view(), name='wallet-recharge'),
    path(
        'wallet/recharge/callback/',
        RechargeCallbackView.as_view(),
        name='wallet-recharge-callback',
    ),
]
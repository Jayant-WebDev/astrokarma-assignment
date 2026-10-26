from django.urls import path

from .views import (
    AcceptSessionView,
    AssignSessionView,
    BillSessionView,
    CreateSessionView,
    EndSessionView,
    StartSessionView,
)

urlpatterns = [
    path('sessions/', CreateSessionView.as_view(), name='session-create'),
    path('sessions/<int:pk>/assign/', AssignSessionView.as_view(), name='session-assign'),
    path('sessions/<int:pk>/accept/', AcceptSessionView.as_view(), name='session-accept'),
    path('sessions/<int:pk>/start/', StartSessionView.as_view(), name='session-start'),
    path('sessions/<int:pk>/end/', EndSessionView.as_view(), name='session-end'),
    path('sessions/<int:pk>/bill/', BillSessionView.as_view(), name='session-bill'),
]
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BatchSyncView, MemberViewSet, SyncHistoryView

router = DefaultRouter()
router.register("records", MemberViewSet, basename="member")

urlpatterns = [
    path("sync/", BatchSyncView.as_view(), name="member_batch_sync"),
    path("sync/history/", SyncHistoryView.as_view(), name="member_sync_history"),
] + router.urls

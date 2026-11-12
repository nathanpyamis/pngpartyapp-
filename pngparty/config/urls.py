from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.geo.views import ElectorateLookupView
from apps.members.views import VerifyMemberView

urlpatterns = [
    path("admin/", admin.site.urls),

    # --- API (field agent PWA) ---
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/geo/electorates/", ElectorateLookupView.as_view(), name="electorate_lookup"),
    path("api/members/", include("apps.members.api_urls")),

    # --- Coordinator / executive portal (session auth) ---
    path("portal/members/", include("apps.members.portal_urls")),

    # --- Field agent PWA shell ---
    path("agent/", include("apps.pwa.urls")),

    # --- Public card verification (QR target) ---
    path("verify/<uuid:member_id>/", VerifyMemberView.as_view(), name="verify_member"),

    # --- Public website (Module A, next step) ---
    path("", include("apps.cms.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

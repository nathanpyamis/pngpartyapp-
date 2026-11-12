from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Electorate, Province


class ElectorateLookupView(APIView):
    """
    Compact lookup table the PWA caches for offline dropdowns.
    ~110 rows nationwide, so it is sent whole; the client filters.
    `assigned_electorate_id` lets the form preselect the agent's electorate.
    """

    def get(self, request):
        provinces = list(Province.objects.values("id", "name", "code", "region"))
        electorates = list(
            Electorate.objects.values("id", "name", "electorate_type", "province_id")
        )
        user = request.user
        return Response({
            "provinces": provinces,
            "electorates": electorates,
            "assigned_province_id": user.assigned_province_id,
            "assigned_electorate_id": user.assigned_electorate_id,
            "role": user.role,
        })

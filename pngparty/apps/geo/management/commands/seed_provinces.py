"""
python manage.py seed_provinces

Seeds the 22 provinces and one Provincial electorate each. Open electorates
are NOT seeded here: load the official PNGEC list for 2027 (boundaries may be
redrawn before the election) via the admin or a fixture, e.g.
    python manage.py loaddata open_electorates_2027.json
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.geo.models import Electorate, Province, Region

PROVINCES = [
    # (name, code, region)
    ("Chimbu", "CHM", Region.HIGHLANDS),
    ("Eastern Highlands", "EHP", Region.HIGHLANDS),
    ("Enga", "ENG", Region.HIGHLANDS),
    ("Hela", "HEL", Region.HIGHLANDS),
    ("Jiwaka", "JWK", Region.HIGHLANDS),
    ("Southern Highlands", "SHP", Region.HIGHLANDS),
    ("Western Highlands", "WHP", Region.HIGHLANDS),
    ("East Sepik", "ESP", Region.MOMASE),
    ("Madang", "MAD", Region.MOMASE),
    ("Morobe", "MOR", Region.MOMASE),
    ("West Sepik (Sandaun)", "WSP", Region.MOMASE),
    ("Central", "CEN", Region.SOUTHERN),
    ("Gulf", "GUL", Region.SOUTHERN),
    ("Milne Bay", "MBP", Region.SOUTHERN),
    ("National Capital District", "NCD", Region.SOUTHERN),
    ("Oro (Northern)", "ORO", Region.SOUTHERN),
    ("Western", "WPD", Region.SOUTHERN),
    ("Autonomous Region of Bougainville", "ARB", Region.NGI),
    ("East New Britain", "ENB", Region.NGI),
    ("Manus", "MAN", Region.NGI),
    ("New Ireland", "NIP", Region.NGI),
    ("West New Britain", "WNB", Region.NGI),
]


class Command(BaseCommand):
    help = "Seed the 22 provinces and their Provincial (regional) electorates."

    @transaction.atomic
    def handle(self, *args, **opts):
        for name, code, region in PROVINCES:
            prov, _ = Province.objects.update_or_create(code=code, defaults={"name": name, "region": region})
            Electorate.objects.get_or_create(
                province=prov, name=f"{name} Provincial",
                defaults={"electorate_type": Electorate.Type.PROVINCIAL},
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(PROVINCES)} provinces."))

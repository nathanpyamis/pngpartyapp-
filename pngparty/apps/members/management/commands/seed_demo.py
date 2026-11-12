"""
Demo data for local test runs: sample members (with placeholder photos),
news posts and policy summaries. Never run this against production.

    python manage.py seed_demo            # adds data if none exists yet
    python manage.py seed_demo --reset    # deletes earlier demo data first
"""
import io
from datetime import date, timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.accounts.models import User
from apps.cms.models import NewsPost, PolicyDocument
from apps.geo.models import Province
from apps.members.models import Member

DEMO_TAG = "DEMO"  # stored in llg_ward so demo members are easy to find and remove

# (full name, gender, province code, ward, village, verified?)
MEMBERS = [
    ("Mary Kila", "F", "NCD", "Moresby North-East", "Gerehu Stage 2", True),
    ("John Wari", "M", "NCD", "Moresby South", "Hanuabada", True),
    ("Grace Tomu", "F", "MOR", "Lae Urban", "Eriku", True),
    ("Peter Kaupa", "M", "WHP", "Mount Hagen Urban", "Kagamuga", True),
    ("Ruth Siune", "F", "EHP", "Goroka Urban", "North Goroka", True),
    ("Daniel Pomat", "M", "ESP", "Wewak Urban", "Kreer", True),
    ("Agnes Moses", "F", "MBP", "Alotau Urban", "Wagawaga", True),
    ("Samuel Ume", "M", "ENB", "Kokopo-Vunamami", "Takubar", True),
    ("Helen Bais", "F", "MAD", "Madang Urban", "Newtown", False),
    ("Joseph Kuman", "M", "SHP", "Mendi Urban", "Tente", False),
    ("Lucy Aiwa", "F", "WSP", "Daru Urban", "Daru Island", False),
]


def placeholder_photo(name: str, seed: int) -> bytes:
    """A plain 300x375 silhouette with initials, so the card shows a photo slot filled."""
    bgs = [(214, 222, 230), (230, 220, 205), (210, 228, 214), (228, 214, 220)]
    w, h = 300, 375
    img = Image.new("RGB", (w, h), bgs[seed % len(bgs)])
    d = ImageDraw.Draw(img)
    body = (70, 70, 80)
    d.ellipse((95, 70, 205, 190), fill=body)                 # head
    d.rounded_rectangle((45, 205, 255, 420), 90, fill=body)  # shoulders
    initials = "".join(p[0] for p in name.split()[:2]).upper()
    d.text((w // 2, 130), initials, fill=(240, 240, 240), anchor="mm", font_size=48)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


NEWS = [
    ("RALLY", "Membership drive reaches every province",
     "Field agents are now registering members in all 22 provinces, including areas with no phone signal.",
     "Our field agents use the offline registration app to sign up members in villages, markets and "
     "church halls. Records are saved on the phone and uploaded when the agent next has signal.\n\n"
     "Each new member is checked by their provincial coordinator before a membership card is printed."),
    ("NEWS", "New membership cards with QR verification",
     "Every verified member receives a printed card that anyone can check by scanning its QR code.",
     "Scanning the code on a card opens a page on the party website that confirms whether the card "
     "belongs to a verified member. The page shows the member's name, photo and electorate only. "
     "No phone numbers, NID numbers or home addresses are ever shown."),
    ("PRESS", "Provincial coordinators appointed",
     "Coordinators will review new registrations and organise card printing in each province.",
     "Provincial coordinators are responsible for reviewing members registered in their province, "
     "resolving possible duplicate registrations and printing membership cards."),
]

POLICIES = [
    ("ECONOMY", "Jobs and small business", "Sample text: support for SMEs, local ownership and access to credit."),
    ("AGRICULTURE", "Farmers and markets", "Sample text: roads to market, extension officers and fair prices for growers."),
    ("INFRA", "Roads, power and connectivity", "Sample text: maintained trunk roads, rural electrification and mobile coverage."),
    ("EDUCATION", "Schools that work", "Sample text: teacher housing, school supplies and technical colleges."),
    ("HEALTH", "Health care close to home", "Sample text: staffed aid posts, medicine supply and maternal health."),
    ("LAW_ORDER", "Safe communities", "Sample text: community policing, village courts and youth programmes."),
]


class Command(BaseCommand):
    help = "Load sample members, news and policies for local testing (not for production)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete earlier demo data first.")

    def handle(self, *args, reset=False, **opts):
        if not Province.objects.exists():
            raise CommandError("Run `python manage.py seed_provinces` first.")
        if reset:
            Member.objects.filter(llg_ward__startswith=f"[{DEMO_TAG}]").delete()
            NewsPost.objects.filter(title__in=[t for _, t, _, _ in NEWS]).delete()
            PolicyDocument.objects.filter(summary__startswith="Sample text").delete()

        verifier = User.objects.filter(is_superuser=True).first()
        made = 0
        if not Member.objects.filter(llg_ward__startswith=f"[{DEMO_TAG}]").exists():
            for i, (name, gender, code, ward, village, verified) in enumerate(MEMBERS):
                prov = Province.objects.filter(code=code).first() or Province.objects.first()
                electorate = prov.electorates.first()
                if electorate is None:
                    continue
                m = Member(
                    full_name=name, gender=gender, electorate=electorate,
                    llg_ward=f"[{DEMO_TAG}] {ward}", village_or_street=village,
                    phone_number=f"7{i:07d}", nid_number=f"DEMO{i:06d}",
                    date_of_birth=date(1975 + i * 2, (i % 12) + 1, 10 + i),
                    source=Member.Source.ADMIN,
                    client_created_at=timezone.now() - timedelta(days=30 - i),
                )
                m.save()
                m.photo.save(f"{m.pk}.jpg", ContentFile(placeholder_photo(name, i)), save=True)
                if verified:
                    m.verify(verifier)
                made += 1

            # One possible duplicate so the review flag shows in the admin.
            original = Member.objects.get(full_name="Mary Kila")
            Member.objects.create(
                full_name="Mary Kila", gender="F", electorate=original.electorate,
                llg_ward=f"[{DEMO_TAG}] Moresby North-East", village_or_street="Gerehu",
                phone_number=original.phone_number, nid_number=original.nid_number,
                source=Member.Source.FIELD, review_flag=Member.ReviewFlag.DUPLICATE_NID,
                duplicate_of=original,
            )
            made += 1

        news = 0
        for days_ago, (kind, title, summary, body) in enumerate(NEWS):
            _, created = NewsPost.objects.get_or_create(
                title=title,
                defaults={"kind": kind, "summary": summary, "body": body, "is_published": True,
                          "published_at": timezone.now() - timedelta(days=days_ago * 4)},
            )
            news += created

        pol = 0
        for order, (pillar, title, summary) in enumerate(POLICIES):
            _, created = PolicyDocument.objects.get_or_create(
                pillar=pillar, title=title, defaults={"summary": summary, "order": order})
            pol += created

        self.stdout.write(self.style.SUCCESS(
            f"Demo data: {made} members, {news} news posts, {pol} policies added."))

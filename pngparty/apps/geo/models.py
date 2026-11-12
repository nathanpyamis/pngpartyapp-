from django.db import models


class Region(models.TextChoices):
    HIGHLANDS = "HIGHLANDS", "Highlands"
    MOMASE = "MOMASE", "Momase"
    SOUTHERN = "SOUTHERN", "Southern"
    NGI = "NGI", "New Guinea Islands"


class Province(models.Model):
    """The 22 provincial-level divisions (incl. NCD and AROB)."""
    name = models.CharField(max_length=80, unique=True)
    # Three-letter code used in membership numbers, e.g. MOR -> PNGP-MOR-A1B2C3
    code = models.CharField(max_length=3, unique=True)
    region = models.CharField(max_length=10, choices=Region.choices)

    class Meta:
        ordering = ["region", "name"]

    def __str__(self):
        return self.name


class Electorate(models.Model):
    class Type(models.TextChoices):
        OPEN = "OPEN", "Open"
        PROVINCIAL = "PROVINCIAL", "Provincial"

    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name="electorates")
    name = models.CharField(max_length=120)
    electorate_type = models.CharField(max_length=10, choices=Type.choices, default=Type.OPEN)

    class Meta:
        ordering = ["province__name", "electorate_type", "name"]
        constraints = [
            models.UniqueConstraint(fields=["province", "name"], name="uniq_electorate_per_province"),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_electorate_type_display()})"

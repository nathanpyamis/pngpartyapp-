from django.db import models
from django.utils.text import slugify


class NewsPost(models.Model):
    class Kind(models.TextChoices):
        NEWS = "NEWS", "News"
        PRESS = "PRESS", "Press release"
        RALLY = "RALLY", "Rally update"

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    kind = models.CharField(max_length=5, choices=Kind.choices, default=Kind.NEWS)
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField()
    cover_image = models.ImageField(upload_to="news/%Y/%m/", blank=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-published_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:220]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class PolicyDocument(models.Model):
    class Pillar(models.TextChoices):
        ECONOMY = "ECONOMY", "Economy"
        AGRICULTURE = "AGRICULTURE", "Agriculture"
        INFRASTRUCTURE = "INFRA", "Infrastructure"
        EDUCATION = "EDUCATION", "Education"
        HEALTH = "HEALTH", "Health"
        LAW_ORDER = "LAW_ORDER", "Law & Order"

    pillar = models.CharField(max_length=12, choices=Pillar.choices)
    title = models.CharField(max_length=200)
    summary = models.TextField()
    pdf = models.FileField(upload_to="policies/", blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["pillar", "order"]

    def __str__(self):
        return f"{self.get_pillar_display()}: {self.title}"

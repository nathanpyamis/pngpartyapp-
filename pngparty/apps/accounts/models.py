from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        AGENT = "AGENT", "Field Agent"
        COORDINATOR = "COORDINATOR", "Provincial Coordinator"
        EXEC = "EXEC", "National Executive"

    phone_number = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.AGENT)
    assigned_province = models.ForeignKey(
        "geo.Province", null=True, blank=True, on_delete=models.SET_NULL, related_name="staff"
    )
    assigned_electorate = models.ForeignKey(
        "geo.Electorate", null=True, blank=True, on_delete=models.SET_NULL, related_name="agents"
    )

    def clean(self):
        super().clean()
        if self.role == self.Role.AGENT and not self.assigned_electorate_id:
            raise ValidationError("Field agents must be assigned an electorate.")
        if self.role == self.Role.COORDINATOR and not self.assigned_province_id:
            raise ValidationError("Coordinators must be assigned a province.")
        if self.assigned_electorate_id:
            # Keep province consistent with electorate
            self.assigned_province_id = self.assigned_electorate.province_id

    @property
    def is_exec(self):
        return self.role == self.Role.EXEC or self.is_superuser

    @property
    def is_coordinator(self):
        return self.role == self.Role.COORDINATOR

    @property
    def is_agent(self):
        return self.role == self.Role.AGENT

from django.db import models


class Card(models.Model):
	external_id = models.CharField(max_length=64, unique=True, db_index=True)
	name = models.CharField(max_length=256, blank=True, null=True)
	data = models.JSONField(default=dict)

	def __str__(self):
		return self.name or str(self.external_id)

# Create your models here.

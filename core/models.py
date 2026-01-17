from django.db import models


class Card(models.Model):
	external_id = models.CharField(max_length=64, unique=True, db_index=True)
	name = models.CharField(max_length=256, blank=True, null=True)
	data = models.JSONField(default=dict)
	is_deleted = models.BooleanField(default=False)

	def __str__(self):
		return self.name or str(self.external_id)

	def get_rating(self):
		d = self.data or {}
		v = d.get("Overall") or d.get("Rating") or "0"
		try:
			return int(str(v))
		except Exception:
			return 0

	def quicksell_price(self):
		rating = self.get_rating()
		# Simple formula: rating * 10
		return rating * 10


class Pack(models.Model):
	name = models.CharField(max_length=256)
	price = models.IntegerField()  # in coins, 0 for free
	num_cards = models.IntegerField(default=5)

	chances = models.JSONField(default=dict)

	def __str__(self):
		return self.name

# Create your models here.

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


class Profile(models.Model):
	coins = models.IntegerField(default=0) 

	def __str__(self):
		return "User Profile"


class UserCard(models.Model):
	profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
	card = models.ForeignKey(Card, on_delete=models.CASCADE)
	quantity = models.IntegerField(default=1)

	class Meta:
		unique_together = ('profile', 'card')

	def __str__(self):
		return f"Profile - {self.card.name}"


class Pack(models.Model):
	name = models.CharField(max_length=256)
	price = models.IntegerField()  # in coins, 0 for free
	num_cards = models.IntegerField(default=5)

	chances = models.JSONField(default=dict)

	def __str__(self):
		return self.name

# Create your models here.

from django.db import models


class Card(models.Model):
	external_id = models.CharField(max_length=64, unique=True, db_index=True)
	name = models.CharField(max_length=256, blank=True, null=True)
	rating = models.IntegerField(blank=True, null=True)
	price = models.CharField(max_length=32, blank=True, null=True)
	skills_moves = models.IntegerField(blank=True, null=True)
	weak_foot = models.IntegerField(blank=True, null=True)
	pace = models.IntegerField(blank=True, null=True)
	shooting = models.IntegerField(blank=True, null=True)
	passing = models.IntegerField(blank=True, null=True)
	dribbling = models.IntegerField(blank=True, null=True)
	defending = models.IntegerField(blank=True, null=True)
	physical = models.IntegerField(blank=True, null=True)
	popularity = models.IntegerField(blank=True, null=True)
	base_stats = models.IntegerField(blank=True, null=True)
	in_game_stats = models.IntegerField(blank=True, null=True)
	revision = models.CharField(max_length=64, blank=True, null=True)
	position = models.CharField(max_length=32, blank=True, null=True)
	work_rate = models.CharField(max_length=32, blank=True, null=True)
	height = models.CharField(max_length=32, blank=True, null=True)
	club = models.CharField(max_length=128, blank=True, null=True)
	country = models.CharField(max_length=64, blank=True, null=True)
	league = models.CharField(max_length=128, blank=True, null=True)
	nation_pic = models.URLField(blank=True, null=True)
	club_pic = models.URLField(blank=True, null=True)
	player_pic = models.URLField(blank=True, null=True)
	is_deleted = models.BooleanField(default=False)

	def __str__(self):
		return self.name or str(self.external_id)

	def get_rating(self):
		return self.rating or 0

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

from django.contrib import admin
from .models import Card


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
	list_display = ("external_id", "name")
	search_fields = ("external_id", "name")

# Register your models here.

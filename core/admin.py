from django.contrib import admin
from .models import Card, Pack


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("external_id", "name", "get_rating", "quicksell_price", "is_deleted")
    search_fields = ("external_id", "name")
    list_filter = ("is_deleted",)

    def get_rating(self, obj):
        return obj.get_rating()

    def quicksell_price(self, obj):
        return obj.quicksell_price()


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "num_cards")
    search_fields = ("name",)
    list_filter = ("price", "num_cards")

# Register your models here.

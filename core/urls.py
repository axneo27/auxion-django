from django.urls import path
from . import views

urlpatterns = [
    path('collection/', views.collection_view, name='collection'),
    path('packs/', views.packs_view, name='packs'),
    path('packs/<int:pack_id>/open/', views.open_pack, name='open_pack'),
    path('quicksell/<int:card_id>/', views.quicksell, name='quicksell'),
    path('delete/<int:card_id>/', views.delete_card, name='delete_card'),
    path('deleted/', views.deleted_cards_view, name='deleted_cards'),
    path('create/', views.create_card_view, name='create_card'),
    path('edit/<int:card_id>/', views.edit_card_view, name='edit_card'),
    path('', views.list_view, name='card_list'),
    path('<str:item_id>/', views.detail_view, name='card_detail'),
]

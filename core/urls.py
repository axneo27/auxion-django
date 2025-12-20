from django.urls import path
from . import views

urlpatterns = [
    path('collection/', views.collection_view, name='collection'),
    path('packs/', views.packs_view, name='packs'),
    path('packs/<int:pack_id>/open/', views.open_pack, name='open_pack'),
    path('quicksell/<int:card_id>/', views.quicksell, name='quicksell'),
    path('', views.list_view, name='card_list'),
    path('<str:item_id>/', views.detail_view, name='card_detail'),
]

from django.urls import path
from . import views

urlpatterns = [
    path('collection/', views.collection_view, name='collection'),
    path('packs/', views.packs_view, name='packs'),
    path('packs/<int:pack_id>/open/', views.open_pack, name='open_pack'),
    path('quicksell/<str:card_id>/', views.quicksell, name='quicksell'),
    # Transfers / Auctions
    path('transfers/', views.transfers_view, name='transfers'),
    path('transfers/my/', views.my_transfers_view, name='my_transfers'),
    path('auction/create/', views.create_auction_view, name='create_auction'),
    path('auction/<str:auction_id>/bid/', views.place_bid_view, name='place_bid'),
    path('auction/<str:auction_id>/buy/', views.buy_now_view, name='buy_now'),
    path('auction/<str:auction_id>/cancel/', views.cancel_auction_view, name='cancel_auction'),
    path('delete/<int:card_id>/', views.delete_card, name='delete_card'),
    path('deleted/', views.deleted_cards_view, name='deleted_cards'),
    path('create/', views.create_card_view, name='create_card'),
    path('edit/<int:card_id>/', views.edit_card_view, name='edit_card'),
    path('auth/google/', views.google_login, name='google_login'),
    path('auth/logout/', views.google_logout, name='google_logout'),
    path('', views.list_view, name='card_list'),
    path('<str:item_id>/', views.detail_view, name='card_detail'),
]

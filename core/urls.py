from django.urls import path
from . import views

urlpatterns = [
    path('', views.list_view, name='card_list'),
    path('<str:item_id>/', views.detail_view, name='card_detail'),
]

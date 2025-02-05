from django.urls import path
from . import views

app_name = 'news'

urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('explore/', views.explore_page, name='explore'),
    path('create/', views.create_news, name='create_news'),
    path('news/<int:pk>/', views.news_detail, name='news_detail'),
    path('news/<int:pk>/like/', views.like_news, name='like_news'),
    path('news/<int:pk>/comment/', views.add_comment, name='add_comment'),
    path('news/<int:pk>/share/', views.share_news, name='share_news'),
    path('news/<int:pk>/edit/', views.edit_news, name='edit_news'),
    path('news/<int:pk>/delete/', views.delete_news, name='delete_news'),
    path('search/', views.search_news, name='search_news'),
    path('notifications/', views.notifications_list, name='notifications'),
    path('notifications/<int:pk>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('user/<str:username>/', views.user_profile, name='user_profile'),
    path('user/<str:username>/follow/', views.follow_user, name='follow_user'),
    path('user/<str:username>/followers/', views.followers_list, name='followers_list'),
    path('user/<str:username>/following/', views.following_list, name='following_list'),
    path('api/world-news/', views.world_news_api, name='world_news_api'),
    path('api/indian-news/', views.indian_news_api, name='indian_news_api'),
    path('hashtag/<str:tag_name>/', views.hashtag_view, name='hashtag'),
    path('settings/', views.profile_settings, name='profile_settings'),
    path('market/', views.market_list, name='market_list'),
    path('api/market-data/', views.market_data_api, name='market_data_api'),
    path('api/user-search/', views.user_search_api, name='user_search_api'),
] 
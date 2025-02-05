from django.contrib import admin
from .models import Profile, News, NewsImage, Comment, Share

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'bio')
    search_fields = ('user__username', 'bio')

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'news_type', 'created_at', 'views')
    list_filter = ('news_type', 'created_at')
    search_fields = ('title', 'content', 'author__username')
    date_hierarchy = 'created_at'

@admin.register(NewsImage)
class NewsImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'caption', 'uploaded_at')
    search_fields = ('caption',)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'news', 'created_at', 'parent')
    list_filter = ('created_at',)
    search_fields = ('content', 'author__username')

@admin.register(Share)
class ShareAdmin(admin.ModelAdmin):
    list_display = ('user', 'news', 'shared_at')
    list_filter = ('shared_at',)
    search_fields = ('user__username', 'news__title')

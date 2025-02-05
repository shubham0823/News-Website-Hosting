from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from .models import News, Comment, Profile, NewsImage, Notification, Share, Hashtag
import requests
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count
from .forms import NewsForm
from django.db import models
from django.utils import timezone
import os
import uuid

def get_market_data():
    import requests
    
    # Finnhub API configuration
    API_KEY = 'cu4gcr1r01qna2rnb3t0cu4gcr1r01qna2rnb3tg'
    BASE_URL = 'https://finnhub.io/api/v1'
    
    # List of stock symbols to track
    STOCK_SYMBOLS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'META']
    # List of crypto symbols to track
    CRYPTO_SYMBOLS = ['BINANCE:BTCUSDT', 'BINANCE:ETHUSDT', 'BINANCE:BNBUSDT']
    
    stocks_data = []
    crypto_data = []
    
    try:
        # Fetch stock data
        for symbol in STOCK_SYMBOLS:
            quote = requests.get(f'{BASE_URL}/quote', 
                               params={'symbol': symbol, 'token': API_KEY})
            profile = requests.get(f'{BASE_URL}/stock/profile2', 
                                 params={'symbol': symbol, 'token': API_KEY})
            
            if quote.status_code == 200 and profile.status_code == 200:
                quote_data = quote.json()
                profile_data = profile.json()
                
                stocks_data.append({
                    'symbol': symbol,
                    'name': profile_data.get('name', symbol),
                    'price': quote_data.get('c', 0),  # Current price
                    'change_percent': quote_data.get('dp', 0),  # Percent change
                    'market_cap': profile_data.get('marketCapitalization', 0) * 1000000  # Convert to actual value
                })
        
        # Fetch crypto data
        for symbol in CRYPTO_SYMBOLS:
            quote = requests.get(f'{BASE_URL}/quote', 
                               params={'symbol': symbol, 'token': API_KEY})
            
            if quote.status_code == 200:
                quote_data = quote.json()
                clean_symbol = symbol.split(':')[1][:3]  # Extract first 3 chars after BINANCE:
                
                crypto_data.append({
                    'symbol': clean_symbol,
                    'name': f'{clean_symbol}/USDT',
                    'price': quote_data.get('c', 0),
                    'change_percent': quote_data.get('dp', 0),
                    'market_cap': 0  # Finnhub doesn't provide market cap for crypto
                })
    
    except Exception as e:
        print(f"Error fetching market data: {e}")
    
    return {
        'stocks': stocks_data,
        'crypto': crypto_data
    }

def landing_page(request):
    # Get the 3 most recent news posts for trending section
    trending_news = News.objects.select_related('author', 'author__profile').prefetch_related(
        'images', 'likes', 'comments', 'shares', 'hashtags'
    ).order_by('-created_at')[:3]
    
    # Get all news for the main feed
    news_feed = News.objects.select_related('author', 'author__profile').prefetch_related(
        'images', 'likes', 'comments', 'shares', 'hashtags'
    ).order_by('-created_at')[3:]  # Skip the first 3 as they're in trending
    
    # Get trending hashtags for world news
    global_trending_tags = (
        Hashtag.objects
        .filter(news_posts__content__iregex=r'\b(world|global|international)\b')
        .order_by('-total_count')[:5]
    )
    
    # Get trending hashtags for Indian news
    india_trending_tags = (
        Hashtag.objects
        .filter(news_posts__content__iregex=r'\b(india|indian)\b')
        .order_by('-total_count')[:5]
    )
    
    # Fetch market data
    market_data = get_market_data()
    
    # Fetch world news from API
    api_key = settings.WORLD_NEWS_API_KEY
    world_news = []
    indian_news = []

    try:
        # Fetch world news
        world_response = requests.get(
            f'https://api.worldnewsapi.com/search-news',
            params={
                'api-key': api_key,
                'text': 'world',
                'number': 5
            }
        )
        if world_response.status_code == 200:
            world_news = world_response.json().get('news', [])

        # Fetch Indian news
        indian_response = requests.get(
            f'https://api.worldnewsapi.com/search-news',
            params={
                'api-key': api_key,
                'text': 'India',
                'number': 5
            }
        )
        if indian_response.status_code == 200:
            indian_news = indian_response.json().get('news', [])
    except Exception as e:
        print(f"Error fetching news: {str(e)}")

    context = {
        'market_data': market_data,
        'world_news': world_news,
        'indian_news': indian_news,
        'trending_news': trending_news,
        'news_feed': news_feed,
        'global_trending_tags': global_trending_tags,
        'india_trending_tags': india_trending_tags,
        'debug': settings.DEBUG,
    }

    return render(request, 'news/landing_page.html', context)

@login_required
def explore_page(request):
    # Get the filter type from query parameters
    active_filter = request.GET.get('filter', 'trending')
    
    # Base queryset with all necessary related data
    news_queryset = News.objects.select_related('author', 'author__profile')\
        .prefetch_related('likes', 'comments', 'shares', 'images')\
        .annotate(engagement_score=Count('likes') + Count('comments') + Count('shares'))
    
    if active_filter == 'trending':
        # Get trending news based on engagement score in the last 7 days
        seven_days_ago = timezone.now() - timezone.timedelta(days=7)
        news_items = news_queryset.filter(created_at__gte=seven_days_ago)\
            .order_by('-engagement_score', '-created_at')
    elif active_filter == 'for_you':
        # Get personalized news based on user's interests
        followed_users = request.user.profile.following.values_list('user', flat=True)
        liked_news = request.user.liked_news.values_list('author', flat=True)
        interested_hashtags = Hashtag.objects.filter(
            news_posts__in=request.user.liked_news.all()
        ).values_list('name', flat=True)
        
        news_items = news_queryset.filter(
            Q(author__in=followed_users) |  # Posts from followed users
            Q(author__in=liked_news) |      # Posts from authors whose content user has liked
            Q(hashtags__name__in=interested_hashtags)  # Posts with hashtags user has interacted with
        ).distinct().order_by('-created_at')
    else:  # followers
        # Get news only from followed users
        followed_users = request.user.profile.following.values_list('user', flat=True)
        news_items = news_queryset.filter(author__in=followed_users).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(news_items, 12)  # Show 12 news items per page
    page = request.GET.get('page')
    try:
        news_items = paginator.page(page)
    except PageNotAnInteger:
        news_items = paginator.page(1)
    except EmptyPage:
        news_items = paginator.page(paginator.num_pages)
    
    context = {
        'news_items': news_items,
        'active_filter': active_filter
    }
    return render(request, 'news/explore.html', context)

@login_required
def create_news(request):
    if request.method == 'POST':
        try:
            form = NewsForm(request.POST, request.FILES)
            if form.is_valid():
                news = form.save(commit=False)
                news.author = request.user
                
                # Get the media type for short format
                media_type = form.cleaned_data.get('media_type')
                
                # Ensure media directories exist
                video_path = os.path.join(settings.MEDIA_ROOT, 'news_videos')
                image_path = os.path.join(settings.MEDIA_ROOT, 'news_images')
                os.makedirs(video_path, exist_ok=True)
                os.makedirs(image_path, exist_ok=True)
                
                # Save the news object first
                news.save()
                
                if news.news_type == 'short':
                    if media_type == 'video' and request.FILES.get('video'):
                        video_file = request.FILES['video']
                        file_ext = os.path.splitext(video_file.name)[1]
                        unique_filename = f"{uuid.uuid4()}{file_ext}"
                        news.video.save(unique_filename, video_file, save=True)
                    elif media_type == 'image' and request.FILES.getlist('images'):
                        image = request.FILES.getlist('images')[0]
                        NewsImage.objects.create(
                            news=news,
                            image=image,
                            caption=f"Image for {news.title}"
                        )
                else:  # Long format
                    if request.FILES.get('video'):
                        video_file = request.FILES['video']
                        file_ext = os.path.splitext(video_file.name)[1]
                        unique_filename = f"{uuid.uuid4()}{file_ext}"
                        news.video.save(unique_filename, video_file, save=True)
                    
                    for image in request.FILES.getlist('images'):
                        NewsImage.objects.create(
                            news=news,
                            image=image,
                            caption=f"Image for {news.title}"
                        )
                
                # Process hashtags and tagged users
                hashtags = form.cleaned_data.get('hashtags', '')
                news.process_hashtags(hashtags)
                tagged_users = form.cleaned_data.get('tagged_users', '')
                news.process_tagged_users(tagged_users)
                
                messages.success(request, 'News article created successfully!')
                return redirect('news:news_detail', pk=news.pk)
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
        except Exception as e:
            messages.error(request, f'Error creating news article: {str(e)}')
            if 'news' in locals():
                news.delete()  # Clean up if there was an error
    else:
        form = NewsForm()
    
    return render(request, 'news/create_news.html', {'form': form})

def news_detail(request, pk):
    news = get_object_or_404(News, pk=pk)
    # Increment view count
    news.views += 1
    news.save()
    
    comments = news.comments.filter(parent=None)  # Get only top-level comments
    
    # Debug information
    images = news.images.all()
    print(f"Number of images for news {pk}: {images.count()}")  # Debug log
    for img in images:
        print(f"Image {img.id}: URL={img.image.url}, Path={img.image.path}")  # Debug log
    
    context = {
        'news': news,
        'comments': comments,
        'debug': settings.DEBUG,
    }
    return render(request, 'news/news_detail.html', context)

@login_required
def like_news(request, pk):
    news = get_object_or_404(News, pk=pk)
    if request.user in news.likes.all():
        news.likes.remove(request.user)
        liked = False
    else:
        news.likes.add(request.user)
        liked = True
        # Create notification
        if request.user != news.author:
            Notification.objects.create(
                recipient=news.author,
                notification_type='like',
                actor=request.user,
                content_type=ContentType.objects.get_for_model(news),
                object_id=news.id
            )
    
    return JsonResponse({
        'liked': liked,
        'likes_count': news.likes.count()
    })

@login_required
def add_comment(request, pk):
    if request.method == 'POST':
        news = get_object_or_404(News, pk=pk)
        content = request.POST.get('content')
        parent_id = request.POST.get('parent_id')
        
        if parent_id:
            parent_comment = get_object_or_404(Comment, id=parent_id)
            comment = Comment.objects.create(
                news=news,
                author=request.user,
                content=content,
                parent=parent_comment
            )
            # Create notification for reply
            if request.user != parent_comment.author:
                Notification.objects.create(
                    recipient=parent_comment.author,
                    notification_type='comment',
                    actor=request.user,
                    content_type=ContentType.objects.get_for_model(comment),
                    object_id=comment.id
                )
        else:
            comment = Comment.objects.create(
                news=news,
                author=request.user,
                content=content
            )
            # Create notification for comment
            if request.user != news.author:
                Notification.objects.create(
                    recipient=news.author,
                    notification_type='comment',
                    actor=request.user,
                    content_type=ContentType.objects.get_for_model(comment),
                    object_id=comment.id
                )
        
        return JsonResponse({
            'status': 'success',
            'comment_id': comment.id,
            'author': comment.author.username,
            'content': comment.content,
            'created_at': comment.created_at.strftime('%B %d, %Y %H:%M')
        })
    
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def share_news(request, pk):
    news = get_object_or_404(News, pk=pk)
    share = news.shares.create(user=request.user)
    
    # Create notification
    if request.user != news.author:
        Notification.objects.create(
            recipient=news.author,
            notification_type='share',
            actor=request.user,
            content_type=ContentType.objects.get_for_model(share),
            object_id=share.id
        )
    
    return JsonResponse({
        'status': 'success',
        'shares_count': news.shares.count()
    })

@login_required
def notifications_list(request):
    notifications = request.user.notifications.all()
    return render(request, 'news/notifications.html', {'notifications': notifications})

@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'status': 'success'})

@login_required
def mark_all_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return JsonResponse({'status': 'success'})

@login_required
def search_news(request):
    query = request.GET.get('q', '')
    news_type = request.GET.get('type', 'all')
    
    news_list = News.objects.all()
    
    if query:
        news_list = news_list.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(author__username__icontains=query)
        )
    
    if news_type != 'all':
        news_list = news_list.filter(news_type=news_type)
    
    news_list = news_list.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(news_list, 12)  # Show 12 news articles per page
    page = request.GET.get('page')
    news_articles = paginator.get_page(page)
    
    context = {
        'news_articles': news_articles,
        'query': query,
        'news_type': news_type,
    }
    
    return render(request, 'news/search_results.html', context)

@login_required
def follow_user(request, username):
    user_to_follow = get_object_or_404(User, username=username)
    
    if request.user == user_to_follow:
        messages.error(request, "You cannot follow yourself.")
        return JsonResponse({'status': 'error', 'message': 'You cannot follow yourself'})
    
    if request.method == 'POST':
        if request.user.profile.following.filter(user=user_to_follow).exists():
            # Unfollow
            request.user.profile.following.remove(user_to_follow.profile)
            is_following = False
            action = 'unfollowed'
        else:
            # Follow
            request.user.profile.following.add(user_to_follow.profile)
            is_following = True
            action = 'followed'
            
            # Create notification for the followed user
            Notification.objects.create(
                recipient=user_to_follow,
                notification_type='follow',
                actor=request.user,
                content_type=ContentType.objects.get_for_model(Profile),
                object_id=user_to_follow.profile.id
            )
        
        return JsonResponse({
            'status': 'success',
            'is_following': is_following,
            'follower_count': user_to_follow.profile.followers.count(),
            'message': f'Successfully {action} {user_to_follow.username}'
        })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@login_required
def user_profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    user_profile = profile_user.profile
    news_list = News.objects.filter(author=profile_user).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(news_list, 10)
    page = request.GET.get('page')
    news_items = paginator.get_page(page)
    
    is_following = request.user.is_authenticated and request.user.profile.following.filter(user=profile_user).exists()
    
    context = {
        'profile_user': profile_user,
        'user_profile': user_profile,
        'news_items': news_items,
        'is_following': is_following,
        'followers_count': user_profile.followers.count(),
        'following_count': user_profile.following.count()
    }
    return render(request, 'news/user_profile.html', context)

@login_required
def followers_list(request, username):
    user = get_object_or_404(User, username=username)
    followers = user.profile.followers.all()
    return render(request, 'news/followers.html', {'user': user, 'followers': followers})

@login_required
def following_list(request, username):
    user = get_object_or_404(User, username=username)
    following = user.profile.following.all()
    return render(request, 'news/following.html', {'user': user, 'following': following})

@login_required
def edit_news(request, pk):
    news = get_object_or_404(News, pk=pk)
    
    # Check if user is the author
    if news.author != request.user:
        messages.error(request, "You don't have permission to edit this news article.")
        return redirect('news:news_detail', pk=pk)
    
    if request.method == 'POST':
        form = NewsForm(request.POST, request.FILES, instance=news)
        if form.is_valid():
            news = form.save(commit=False)
            
            # Handle media based on news type and media type
            media_type = form.cleaned_data.get('media_type')
            
            if news.news_type == 'short':
                if media_type == 'video' and request.FILES.get('video'):
                    news.video = request.FILES['video']
                elif media_type == 'image':
                    # Handle single image upload for short format
                    uploaded_images = request.FILES.getlist('images')
                    if uploaded_images:
                        # Delete existing images
                        news.images.all().delete()
                        NewsImage.objects.create(
                            news=news,
                            image=uploaded_images[0],
                            caption=f"Image for {news.title}"
                        )
                elif media_type == 'none':
                    # Remove all media
                    news.video = None
                    news.images.all().delete()
            else:  # Long format
                if request.FILES.get('video'):
                    news.video = request.FILES['video']
                
                # Handle multiple images
                uploaded_images = request.FILES.getlist('images')
                if uploaded_images:
                    news.images.all().delete()  # Remove existing images
                    for image in uploaded_images:
                        NewsImage.objects.create(
                            news=news,
                            image=image,
                            caption=f"Image for {news.title}"
                        )
            
            news.save()
            messages.success(request, 'News article updated successfully!')
            return redirect('news:news_detail', pk=news.pk)
    else:
        form = NewsForm(instance=news)
        # Set initial media type
        if news.news_type == 'short':
            if news.video:
                form.initial['media_type'] = 'video'
            elif news.images.exists():
                form.initial['media_type'] = 'image'
            else:
                form.initial['media_type'] = 'none'
    
    return render(request, 'news/edit_news.html', {'form': form, 'news': news})

@login_required
def delete_news(request, pk):
    news = get_object_or_404(News, pk=pk)
    
    # Check if user is the author
    if news.author != request.user:
        messages.error(request, "You don't have permission to delete this news article.")
        return redirect('news:news_detail', pk=pk)
    
    if request.method == 'POST':
        # Delete associated images and video
        news.images.all().delete()
        if news.video:
            news.video.delete()
        
        # Delete the news article
        news.delete()
        messages.success(request, 'News article deleted successfully!')
        return redirect('news:landing_page')
    
    return render(request, 'news/delete_news.html', {'news': news})

def world_news_api(request):
    page = int(request.GET.get('page', 1))
    api_key = settings.WORLD_NEWS_API_KEY
    
    try:
        response = requests.get(
            f'https://api.worldnewsapi.com/search-news',
            params={
                'api-key': api_key,
                'text': 'world',
                'number': 5,
                'offset': (page - 1) * 5
            }
        )
        if response.status_code == 200:
            data = response.json()
            return JsonResponse({
                'news': data.get('news', []),
                'has_more': len(data.get('news', [])) == 5
            })
    except Exception as e:
        print(f"Error fetching world news: {str(e)}")
    
    return JsonResponse({'news': [], 'has_more': False})

def indian_news_api(request):
    page = int(request.GET.get('page', 1))
    api_key = settings.WORLD_NEWS_API_KEY
    
    try:
        response = requests.get(
            f'https://api.worldnewsapi.com/search-news',
            params={
                'api-key': api_key,
                'text': 'India',
                'number': 5,
                'offset': (page - 1) * 5
            }
        )
        if response.status_code == 200:
            data = response.json()
            return JsonResponse({
                'news': data.get('news', []),
                'has_more': len(data.get('news', [])) == 5
            })
    except Exception as e:
        print(f"Error fetching Indian news: {str(e)}")
    
    return JsonResponse({'news': [], 'has_more': False})

def hashtag_view(request, tag_name):
    hashtag = get_object_or_404(Hashtag, name=tag_name)
    news_list = News.objects.filter(hashtags=hashtag).order_by('-created_at')
    
    paginator = Paginator(news_list, 12)  # Show 12 news articles per page
    page = request.GET.get('page')
    news_articles = paginator.get_page(page)
    
    context = {
        'hashtag': hashtag,
        'news_articles': news_articles,
    }
    
    return render(request, 'news/hashtag.html', context)

@login_required
def profile_settings(request):
    if request.method == 'POST' and request.FILES.get('avatar'):
        profile = request.user.profile
        profile.avatar = request.FILES['avatar']
        profile.save()
        messages.success(request, 'Profile photo updated successfully!')
        return redirect('news:profile_settings')
    
    return render(request, 'news/profile_settings.html')

def market_list(request):
    """View for the market list page"""
    return render(request, 'news/market_list.html')

def market_data_api(request):
    """API endpoint for market data"""
    market_data = get_market_data()
    return JsonResponse(market_data)

def user_search_api(request):
    """API endpoint for searching users for tagging"""
    query = request.GET.get('q', '')
    if query:
        users = User.objects.filter(username__icontains=query)[:5]
        return JsonResponse({
            'users': [{
                'username': user.username,
                'avatar': user.profile.avatar.url
            } for user in users]
        })
    return JsonResponse({'users': []})

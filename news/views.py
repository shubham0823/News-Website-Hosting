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
from django.db.models import Q, Count, ExpressionWrapper, F, FloatField, Case, When
from django.db.models.functions import Extract, Now
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
def follow_user(request, username):
    """Handle follow/unfollow functionality"""
    if request.method == 'POST':
        user_to_follow = get_object_or_404(User, username=username)
        user_profile = request.user.profile
        
        # Check if already following
        is_following = user_profile in user_to_follow.profile.followers.all()
        
        if is_following:
            # Unfollow
            user_to_follow.profile.followers.remove(user_profile)
            # Create notification for unfollow
            Notification.objects.filter(
                recipient=user_to_follow,
                notification_type='follow',
                actor=request.user,
            ).delete()
        else:
            # Follow
            user_to_follow.profile.followers.add(user_profile)
            # Create notification for new follow
            Notification.objects.create(
                recipient=user_to_follow,
                notification_type='follow',
                actor=request.user,
                content_type=ContentType.objects.get_for_model(user_to_follow),
                object_id=user_to_follow.id
            )
        
        return JsonResponse({
            'status': 'success',
            'is_following': not is_following,
            'followers_count': user_to_follow.profile.followers.count()
        })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

def followers_list(request, username):
    """Display list of followers for a user"""
    user = get_object_or_404(User, username=username)
    followers = user.profile.followers.select_related('user').all()
    
    context = {
        'profile_user': user,
        'users_list': followers,
        'list_type': 'Followers'
    }
    
    return render(request, 'news/users_list.html', context)

def following_list(request, username):
    """Display list of users being followed"""
    user = get_object_or_404(User, username=username)
    following = user.profile.following.select_related('user').all()
    
    context = {
        'profile_user': user,
        'users_list': following,
        'list_type': 'Following'
    }
    
    return render(request, 'news/users_list.html', context)

@login_required
def explore_page(request):
    """View for the explore page"""
    return render(request, 'news/explore.html')

def api_news(request):
    """API endpoint for filtered news"""
    from django.db.models import Count, F, FloatField, ExpressionWrapper
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.db.models import Q

    filter_type = request.GET.get('filter', 'trending')
    page = int(request.GET.get('page', 1))
    per_page = 12

    # Base queryset with all related data
    news_list = News.objects.select_related(
        'author', 
        'author__profile'
    ).prefetch_related(
        'images', 
        'likes', 
        'comments',
        'shares',
        'hashtags'
    ).all()

    # Apply filters
    if filter_type == 'trending':
        # Calculate trending score based on likes, comments, shares, and recency
        news_list = news_list.annotate(
            hours_since_created=ExpressionWrapper(
                (Now() - F('created_at')) / 3600000000,
                output_field=FloatField()
            ),
            engagement_score=ExpressionWrapper(
                (Count('likes') * 2 + Count('comments') * 3 + Count('shares') * 4) /
                (F('hours_since_created') + 2),
                output_field=FloatField()
            )
        ).order_by('-engagement_score')
    elif filter_type == 'for-you':
        if request.user.is_authenticated:
            # Show personalized news based on:
            # 1. News from followed users (higher weight)
            # 2. News user has liked
            # 3. News with hashtags similar to what user has interacted with
            following_users = request.user.profile.following.values_list('user', flat=True)
            liked_news = request.user.liked_news.all()
            interacted_hashtags = Hashtag.objects.filter(
                Q(news_posts__in=liked_news) |
                Q(news_posts__author__in=following_users)
            ).distinct()

            news_list = news_list.annotate(
                relevance_score=ExpressionWrapper(
                    Case(
                        When(author__in=following_users, then=10),
                        When(id__in=liked_news.values_list('id', flat=True), then=5),
                        When(hashtags__in=interacted_hashtags, then=3),
                        default=0,
                        output_field=FloatField(),
                    ),
                    output_field=FloatField()
                )
            ).filter(
                Q(author__in=following_users) |
                Q(id__in=liked_news.values_list('id', flat=True)) |
                Q(hashtags__in=interacted_hashtags)
            ).distinct().order_by('-relevance_score', '-created_at')
        else:
            news_list = news_list.none()
    elif filter_type == 'followers':
        if request.user.is_authenticated:
            # Show only news from followed users, ordered by most recent
            following_users = request.user.profile.following.values_list('user', flat=True)
            news_list = news_list.filter(
                author__in=following_users
            ).order_by('-created_at')
        else:
            news_list = news_list.none()

    # Paginate results
    paginator = Paginator(news_list, per_page)
    try:
        news_page = paginator.page(page)
    except (EmptyPage, PageNotAnInteger):
        news_page = paginator.page(1)

    # Format response
    news_data = []
    for news in news_page:
        news_data.append({
            'id': news.id,
            'title': news.title,
            'content': news.content,
            'created_at': news.created_at.strftime('%b %d, %Y'),
            'author': {
                'username': news.author.username,
                'avatar': news.author.profile.avatar.url
            },
            'images': [{'url': img.image.url} for img in news.images.all()],
            'video': news.video.url if news.video else None,
            'likes_count': news.likes.count(),
            'comments_count': news.comments.count(),
            'shares_count': news.shares.count(),
            'views': news.views,
            'news_type': news.news_type,
            'hashtags': [tag.name for tag in news.hashtags.all()]
        })

    return JsonResponse({
        'news': news_data,
        'has_more': news_page.has_next()
    })

@login_required
def create_news(request):
    if request.method == 'POST':
        try:
            # Print request.FILES for debugging
            print("Files in request:", request.FILES)
            
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
                
                try:
                    if news.news_type == 'short':
                        if media_type == 'video' and request.FILES.get('video'):
                            video_file = request.FILES['video']
                            print("Processing video file:", video_file.name)
                            file_ext = os.path.splitext(video_file.name)[1]
                            unique_filename = f"{uuid.uuid4()}{file_ext}"
                            news.video.save(unique_filename, video_file, save=True)
                        elif media_type == 'image' and request.FILES.getlist('images'):
                            image = request.FILES.getlist('images')[0]
                            print("Processing image file:", image.name)
                            NewsImage.objects.create(
                                news=news,
                                image=image,
                                caption=f"Image for {news.title}"
                            )
                    else:  # Long format
                        if request.FILES.get('video'):
                            video_file = request.FILES['video']
                            print("Processing video file:", video_file.name)
                            file_ext = os.path.splitext(video_file.name)[1]
                            unique_filename = f"{uuid.uuid4()}{file_ext}"
                            news.video.save(unique_filename, video_file, save=True)
                        
                        for image in request.FILES.getlist('images'):
                            print("Processing image file:", image.name)
                            NewsImage.objects.create(
                                news=news,
                                image=image,
                                caption=f"Image for {news.title}"
                            )
                except Exception as e:
                    print("Error processing media files:", str(e))
                    news.delete()
                    messages.error(request, f'Error processing media files: {str(e)}')
                    return render(request, 'news/create_news.html', {'form': form})
                
                # Process hashtags and tagged users
                hashtags = form.cleaned_data.get('hashtags', '')
                news.process_hashtags(hashtags)
                tagged_users = form.cleaned_data.get('tagged_users', '')
                news.process_tagged_users(tagged_users)
                
                messages.success(request, 'News article created successfully!')
                return redirect('news:news_detail', pk=news.pk)
            else:
                print("Form errors:", form.errors)
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
        except Exception as e:
            print("Error creating news article:", str(e))
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

def user_profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    user_news = News.objects.filter(author=profile_user).order_by('-created_at')
    
    context = {
        'profile_user': profile_user,
        'user_news': user_news,
    }
    
    return render(request, 'news/user_profile.html', context)

@login_required
def update_profile_picture(request):
    if request.method == 'POST' and request.FILES.get('avatar'):
        try:
            # Get the uploaded file
            avatar = request.FILES['avatar']
            
            # Delete old avatar if it exists (except default)
            if request.user.profile.avatar and 'default' not in request.user.profile.avatar.url:
                if os.path.exists(request.user.profile.avatar.path):
                    os.remove(request.user.profile.avatar.path)
            
            # Save new avatar
            request.user.profile.avatar = avatar
            request.user.profile.save()
            
            return JsonResponse({
                'status': 'success',
                'avatar_url': request.user.profile.avatar.url
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    
    return JsonResponse({
        'status': 'error',
        'message': 'No file uploaded'
    }, status=400)

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
    if request.method == 'POST':
        profile = request.user.profile
        
        # Handle avatar update
        if request.FILES.get('avatar'):
            profile.avatar = request.FILES['avatar']
            messages.success(request, 'Profile photo updated successfully!')
        
        # Handle banner update
        if request.FILES.get('banner'):
            profile.banner = request.FILES['banner']
            messages.success(request, 'Profile banner updated successfully!')
        
        # Handle bio update
        if 'bio' in request.POST:
            profile.bio = request.POST['bio']
            messages.success(request, 'Profile bio updated successfully!')
        
        profile.save()
        return redirect('news:profile_settings')
    
    return render(request, 'news/profile_settings.html')

def market_list(request):
    """View for the market list page"""
    return render(request, 'news/market_list.html')

def market_data_api(request):
    """API endpoint for market data"""
    market_data = get_market_data()
    return JsonResponse(market_data)

def market_news_api(request):
    """API endpoint for market news"""
    try:
        category = request.GET.get('category', 'all')
        page = int(request.GET.get('page', 1))
        per_page = 12

        # Build query based on category
        query = {
            'all': 'market OR stock OR crypto OR economy',
            'stocks': 'stock market',
            'crypto': 'cryptocurrency OR crypto market',
            'economy': 'economy OR economic news',
            'analysis': 'market analysis OR financial analysis'
        }.get(category, 'market')

        response = requests.get(
            'https://api.worldnewsapi.com/search-news',
            params={
                'api-key': settings.WORLD_NEWS_API_KEY,
                'text': query,
                'number': per_page,
                'offset': (page - 1) * per_page,
                'sort': 'publish-time'
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            news_items = data.get('news', [])
            
            # Process and format news items
            formatted_news = [{
                'title': item.get('title'),
                'summary': item.get('text', '')[:200] + '...',
                'url': item.get('url'),
                'image_url': item.get('image', '/static/img/default-news.jpg'),
                'source': item.get('source'),
                'category': category.capitalize(),
                'published_at': item.get('publish_date')
            } for item in news_items]

            return JsonResponse({
                'news': formatted_news,
                'has_more': len(news_items) == per_page
            })
        else:
            return JsonResponse({'error': 'Failed to fetch market news'}, status=response.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

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

def category_news(request, category):
    api_key = settings.WORLD_NEWS_API_KEY
    
    # Map categories to appropriate search parameters
    category_mapping = {
        'india': {
            'text': 'India OR Indian',
            'source-countries': 'in'
        },
        'international': {
            'text': 'world OR global OR international',
            'not-source-countries': 'in'  # Exclude Indian sources
        },
        'stocks': {
            'text': 'stock market OR stocks OR trading OR NYSE OR NASDAQ',
            'categories': 'business'
        }
    }
    
    try:
        params = {
            'api-key': api_key,
            'number': 12,  # Number of articles per page
            'sort': 'publish-time',
            'language': 'en'
        }
        
        # Add category-specific parameters
        if category in category_mapping:
            params.update(category_mapping[category])
        
        response = requests.get(
            'https://api.worldnewsapi.com/search-news',
            params=params
        )
        
        if response.status_code == 200:
            news_data = response.json()
            articles = news_data.get('news', [])
            
            # Format articles to match the template expectations
            formatted_articles = [{
                'title': article.get('title'),
                'description': article.get('text', '')[:200] + '...',
                'urlToImage': article.get('image'),
                'url': article.get('url'),
                'source': {'name': article.get('source')}
            } for article in articles]
        else:
            formatted_articles = []
            
    except Exception as e:
        print(f"Error fetching {category} news: {str(e)}")
        formatted_articles = []
    
    context = {
        'articles': formatted_articles,
        'category': category.replace('-', ' ').title()
    }
    return render(request, 'news/category_news.html', context)

def trending_news(request):
    api_key = settings.WORLD_NEWS_API_KEY
    
    try:
        params = {
            'api-key': api_key,
            'number': 12,
            'sort': 'popularity',  # Sort by popularity for trending news
            'language': 'en'
        }
        
        response = requests.get(
            'https://api.worldnewsapi.com/search-news',
            params=params
        )
        
        if response.status_code == 200:
            news_data = response.json()
            articles = news_data.get('news', [])
            
            # Format articles to match the template expectations
            formatted_articles = [{
                'title': article.get('title'),
                'description': article.get('text', '')[:200] + '...',
                'urlToImage': article.get('image'),
                'url': article.get('url'),
                'source': {'name': article.get('source')}
            } for article in articles]
        else:
            formatted_articles = []
            
    except Exception as e:
        print(f"Error fetching trending news: {str(e)}")
        formatted_articles = []
    
    context = {
        'articles': formatted_articles,
        'category': 'Trending'
    }
    return render(request, 'news/category_news.html', context)

def country_news(request, country_code):
    api_key = settings.WORLD_NEWS_API_KEY
    
    # Map of country codes to full names
    country_names = {
        'us': 'United States',
        'cn': 'China',
        'ru': 'Russia',
        'gb': 'United Kingdom',
        'de': 'Germany',
        'fr': 'France',
        'jp': 'Japan',
        'sa': 'Saudi Arabia',
        'in': 'India',
        'kr': 'South Korea',
        'il': 'Israel',
        'ua': 'Ukraine'
    }
    
    try:
        params = {
            'api-key': api_key,
            'number': 12,
            'source-countries': country_code,
            'language': 'en',
            'sort': 'publish-time'
        }
        
        response = requests.get(
            'https://api.worldnewsapi.com/search-news',
            params=params
        )
        
        if response.status_code == 200:
            news_data = response.json()
            articles = news_data.get('news', [])
            
            formatted_articles = [{
                'title': article.get('title'),
                'description': article.get('text', '')[:200] + '...',
                'urlToImage': article.get('image'),
                'url': article.get('url'),
                'source': {'name': article.get('source')}
            } for article in articles]
        else:
            formatted_articles = []
            
    except Exception as e:
        print(f"Error fetching news for {country_code}: {str(e)}")
        formatted_articles = []
    
    context = {
        'articles': formatted_articles,
        'category': f"{country_names.get(country_code, 'Unknown')} News"
    }
    return render(request, 'news/category_news.html', context)

def major_countries(request):
    countries = {
        'us': 'United States',
        'cn': 'China',
        'ru': 'Russia',
        'gb': 'United Kingdom',
        'de': 'Germany',
        'fr': 'France',
        'jp': 'Japan',
        'sa': 'Saudi Arabia',
        'in': 'India',
        'kr': 'South Korea',
        'il': 'Israel',
        'ua': 'Ukraine'
    }
    
    return render(request, 'news/major_countries.html', {
        'countries': countries
    })

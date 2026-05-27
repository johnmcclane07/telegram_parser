import logging
import time
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from asgiref.sync import async_to_sync
from .parser import parse_telegram_post_url, fetch_comments
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from .models import TelegramPost, TelegramComment
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.core.cache import cache
from django.views.decorators.cache import cache_page


logger = logging.getLogger(__name__)

# ========== ДОМАШНЯЯ СТРАНИЦА ==========

def home_view(request):
    """
    Главная страница
    """
    return render(request, "home.html")

# ========== АВТОРИЗАЦИЯ ==========

def register_view(request):
    """
    Регистрация нового пользователя
    """
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Регистрация прошла успешно!')
            return redirect('home')
    else:
        form = UserCreationForm()
    
    return render(request, 'register.html', {'form': form})

def login_view(request):
    """
    Вход в систему
    """
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Добро пожаловать, {username}!')
                
                return redirect('home')
            else:
                messages.error(request, 'Неверное имя пользователя или пароль')
        else:
            messages.error(request, 'Неверное имя пользователя или пароль')
    else:
        form = AuthenticationForm()
    
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    """
    Выход из системы
    """
    logout(request)
    messages.success(request, 'Вы успешно вышли из системы')
    return redirect('login') 

# ========== ПАРСИНГ КОММЕНТАРИЕВ ==========

@login_required
def post_comments_view(request):

    url = request.GET.get("url")
    context = {
        "comments": [],
        "error": None,
        "url": url,
        "user": request.user,
    }
    page_number = request.GET.get("page")

    if not url:
        context["error"] = "URL поста не указан"
        return render(request, "comments.html", context)

    try:
        channel_id, post_id = parse_telegram_post_url(url)
    except ValueError as e:
        context["error"] = str(e)
        return render(request, "comments.html", context)

    start = time.time()
    try:
        if not page_number:
            comments_raw = async_to_sync(fetch_comments)(channel_id, post_id, request)
            comments = []
            for c in comments_raw:
                comments.append({
                    "sender_username": c.get("sender_username", "Неизвестно"),
                    "date": c.get("date"),
                    "comment_text": c.get("text"),
                    "polarity": c.get("sentiment"),  
                })
            context["comments"] = comments


    except Exception as e:
        logger.error(f"Ошибка при получении комментариев: {e}")
        context["error"] = f"Не удалось получить комментарии: {str(e)}"
        return render(request, "comments.html", context)
    end = time.time()
    logger.info(f"[END] {url} took {round(end-start, 2)}s")

    post = TelegramPost.objects.get(post_id=post_id)
    comments_from_db = TelegramComment.objects.filter(post=post).order_by('date')
    paginator = Paginator(comments_from_db, 20)  
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context["page_obj"] = page_obj

    return render(request, "comments.html", context)

# ========= ИСТОРИЯ ПАРСИНГА ==========

@login_required
def history_view(request):
    query = request.GET.get('search', '').strip()  

    posts = TelegramPost.objects.filter(parsed_by=request.user)

    if query:
        if query.isdigit():
            posts = posts.filter(post_id=query)
        else:
            posts = posts.none()  

    posts = posts.order_by('-created_at')

    context = {
        'posts': posts,
        'search_query': query,
    }
    return render(request, 'history.html', context)

# ========= ИНФОРМАЦИЯ ИЗ ПОСТА ==========

@login_required
def post_delete_view(request, post_id):
    if request.method == 'POST':
        post = get_object_or_404(TelegramPost, id=post_id, parsed_by=request.user)
        post.delete()
        messages.success(request, f'Пост {post.channel}/{post.post_id} успешно удалён.')
    return redirect('history')

@cache_page(60 * 15)  
@login_required
def post_detail(request, post_id):
    post = get_object_or_404(
        TelegramPost.objects.prefetch_related('comments'),
        id=post_id
    )

    comments_qs = post.comments.all().order_by('date')

    stats = comments_qs.aggregate(
        positive=Count('id', filter=Q(sentiment='positive')),
        negative=Count('id', filter=Q(sentiment='negative')),
        neutral=Count('id', filter=Q(sentiment='neutral')),
        phones=Count('id', filter=Q(phone__regex=r'^\+?\d{6,}$')),
        total=Count('id')
    )

    paginator = Paginator(comments_qs, 10)  
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "post": post,
        "comments": page_obj,  
        "channel": post.channel,
        "post_id": post.post_id,
        "positive": stats['positive'],
        "negative": stats['negative'],
        "neutral": stats['neutral'],
        "phones": stats['phones'],
        "length": stats['total'],
    }

    return render(request, "post_detail.html", context)

# ========= СПИСОК ТЕЛЕФОННЫХ НОМЕРОВ ==========

@login_required
def phone_numbers_list(request):
    user = request.user
    query = request.GET.get('search', '').strip()  

    filters = {
        'post__parsed_by__in': [user],
    }

    phone_filter = Q(phone__isnull=False) & ~Q(phone='Unknown')

    if query:
        filters['post__channel__icontains'] = query

    phone_numbers_qs = TelegramComment.objects.filter(phone_filter,**filters).values(
        'phone',
        'post__channel',
        'post__post_id',
        'text',
        'name',
        'username',
        'sentiment',
        'date',
        'post__created_at'
    ).order_by('-post__created_at', '-date') 

    paginator = Paginator(phone_numbers_qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, "phones_list.html", {
        "phone_numbers": page_obj,
        "search_query": query,  
        "query_params": f"&search={query}" if query else ""  
    })

# ========= НЕГАТИВНЫЕ КОММЕНТАРИИ ==========

@login_required
def negative_comments_view(request): 
    user = request.user
    query = request.GET.get('search', '').strip() 

    filters = {
        'post__parsed_by__in': [user],
        'sentiment': 'negative'
    }

    if query:
        filters['post__channel__icontains'] = query

    negative_comments_qs = TelegramComment.objects.filter(**filters).values(
        'post__channel',
        'post__post_id',
        'text',
        'name',
        'username',
        'date'
    ).order_by('-post__created_at', '-date')

    paginator = Paginator(negative_comments_qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "negative_comments": page_obj,
        "search_query": query,
        "query_params": f"&search={query}" if query else ""
    }

    return render(request, "negative_comments.html", context)






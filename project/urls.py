"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import include, path
from django.conf import settings
from telegram_parser.views import home_view, post_comments_view,register_view,login_view,logout_view,history_view,post_delete_view, post_detail, phone_numbers_list, negative_comments_view
urlpatterns = [
    path('', home_view, name='home'),
    path('comments/', post_comments_view, name='post-comments'),
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('history/', history_view, name='history'),
    path('post/<int:post_id>/delete/', post_delete_view, name='post_delete'),
    path("post/<int:post_id>/", post_detail, name="post_detail"),
    path("phone-numbers/", phone_numbers_list, name="phone_numbers_list"),
    path("negative-comments/", negative_comments_view, name="negative"),

    
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

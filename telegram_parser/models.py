from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

class TelegramPost(models.Model):
    parsed_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="parsed_posts"
    )
    channel = models.CharField(max_length=255)
    post_id = models.BigIntegerField()
    date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("channel", "post_id")


    def __str__(self):
        return f"{self.parsed_by.all().first()} — {self.channel}/{self.post_id}"

class TelegramComment(models.Model):
    post = models.ForeignKey(
        TelegramPost,
        on_delete=models.CASCADE,
        related_name="comments"
    )

    comment_id = models.BigIntegerField()

    username = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    text = models.TextField()
    date = models.DateTimeField(null=True, blank=True)

    sentiment = models.CharField(
        max_length=16,
        choices=[
            ("positive", "Positive"),
            ("negative", "Negative"),
            ("neutral", "Neutral"),
        ],
        default="neutral"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("post", "comment_id")

    def __str__(self):
        return f"{self.username}: {self.text[:40]}"

class TelegramSession(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session_data = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

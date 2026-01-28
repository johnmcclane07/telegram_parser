
import logging
import time

from rest_framework.views import APIView
from rest_framework.response import Response
from asgiref.sync import async_to_sync

from .parser import parse_telegram_post_url, fetch_comments

logger = logging.getLogger(__name__)

class PostCommentsView(APIView):
    def get(self, request):
        start = time.time()
        url = request.query_params.get("url")
        if not url:
            return Response({"error": "URL parameter is required"}, status=400)

        try:
            channel_id, post_id = parse_telegram_post_url(url)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        comments = async_to_sync(fetch_comments)(channel_id, post_id)
        end = time.time()
        logger.info(f"[END] {url} took {round(end-start,2)}s")

        return Response(comments)
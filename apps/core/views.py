from django.db import connection
from django.http import HttpResponse
from django.shortcuts import render


def home(request):
    return render(request, "home.html")


def healthz(request):
    """Liveness + database check for Docker and the uptime pinger."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return HttpResponse("db unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")

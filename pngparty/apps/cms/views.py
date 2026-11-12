from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from apps.geo.models import Province
from apps.members.models import Member

from .models import NewsPost, PolicyDocument


def _published_news():
    return NewsPost.objects.filter(is_published=True)


def home(request):
    return render(request, "cms/home.html", {
        "news": _published_news()[:3],
        "policies": PolicyDocument.objects.filter(is_published=True)[:6],
        "verified_members": Member.objects.filter(is_verified=True).count(),
        "provinces_active": Province.objects.filter(
            electorates__members__is_verified=True).distinct().count(),
    })


def about(request):
    return render(request, "cms/about.html")


def policies(request):
    return render(request, "cms/policies.html", {
        "policies": PolicyDocument.objects.filter(is_published=True),
    })


def news_list(request):
    return render(request, "cms/news_list.html", {"news": _published_news()})


def news_detail(request, slug):
    return render(request, "cms/news_detail.html", {
        "post": get_object_or_404(_published_news(), slug=slug),
    })


def join(request):
    provinces = Province.objects.annotate(
        members=Count("electorates__members", filter=Q(electorates__members__is_verified=True)))
    return render(request, "cms/join.html", {"provinces": provinces})

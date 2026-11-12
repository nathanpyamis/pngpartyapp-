# Module A: public website. Candidates directory and contact form still to come.
from django.urls import path

from . import views

app_name = "cms"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("policies/", views.policies, name="policies"),
    path("news/", views.news_list, name="news_list"),
    path("news/<slug:slug>/", views.news_detail, name="news_detail"),
    path("join/", views.join, name="join"),
]

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.cache import never_cache


def app_shell(request):
    return render(request, "pwa/index.html", {"version": settings.PWA_VERSION})


@never_cache
def service_worker(request):
    # Served from /agent/sw.js so its scope is /agent/. Rendered as a template
    # so {% static %} resolves to WhiteNoise's hashed filenames.
    resp = render(request, "pwa/sw.js", {"version": settings.PWA_VERSION},
                  content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/agent/"
    return resp


def manifest(request):
    return render(request, "pwa/manifest.webmanifest", content_type="application/manifest+json")

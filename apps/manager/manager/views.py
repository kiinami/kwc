from django.http import HttpResponse


def healthz(request) -> HttpResponse:
    return HttpResponse("ok", content_type="text/plain")

from django.shortcuts import render

from .models import Correspondant


def correspondant_list(request):
    correspondants = Correspondant.objects.prefetch_related("capabilities").order_by(
        "name"
    )
    return render(
        request,
        "correspondants/index.html",
        {"correspondants": correspondants},
    )

from django.urls import path

from . import api

app_name = "correspondants"

urlpatterns = [
    path(
        "correspondants/<str:name>/capacities",
        api.capacities,
        name="capacities",
    ),
    path(
        "correspondants/<str:name>/capacities/<str:capability_name>",
        api.capability_detail,
        name="capability_detail",
    ),
    path(
        "correspondants/<str:name>/capacities/<str:capability_name>/execute",
        api.capability_execute,
        name="capability_execute",
    ),
]

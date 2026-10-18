from django.urls import path

from . import api, views

app_name = "correspondants"

urlpatterns = [
    path("", views.correspondant_list, name="correspondant_list"),
    path(
        "api/correspondants/<str:name>/capacities",
        api.capacities,
        name="capacities",
    ),
    path(
        "api/correspondants/<str:name>/capacities/<str:capability_name>",
        api.capability_detail,
        name="capability_detail",
    ),
    path(
        "api/correspondants/<str:name>/capacities/<str:capability_name>/execute",
        api.capability_execute,
        name="capability_execute",
    ),
]

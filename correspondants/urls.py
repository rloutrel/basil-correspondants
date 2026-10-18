from django.urls import path

from . import api, views

app_name = "correspondants"

urlpatterns = [
    path("", views.correspondant_list, name="correspondant_list"),
    path("correspondants/add", views.correspondant_create, name="correspondant_create"),
    path(
        "correspondants/<str:name>/edit",
        views.correspondant_edit,
        name="correspondant_edit",
    ),
    path(
        "correspondants/<str:name>/delete",
        views.correspondant_delete,
        name="correspondant_delete",
    ),
    path(
        "correspondants/<str:name>/capabilities/add",
        views.capability_create,
        name="capability_create",
    ),
    path(
        "correspondants/<str:name>/capabilities/<str:capability_name>/edit",
        views.capability_edit,
        name="capability_edit",
    ),
    path(
        "correspondants/<str:name>/capabilities/<str:capability_name>/delete",
        views.capability_delete,
        name="capability_delete",
    ),
    path(
        "correspondants/<str:name>/capabilities/<str:capability_name>/test",
        views.capability_test,
        name="capability_test",
    ),
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

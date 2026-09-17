from django.urls import path

from telegram_hub import views

urlpatterns = [
    path("api/me/telegram/status/", views.api_me_telegram_status, name="api_me_telegram_status"),
    path("api/me/telegram/link-codes/", views.api_me_telegram_link_codes, name="api_me_telegram_link_codes"),
    path("api/me/telegram/links/", views.api_me_telegram_links, name="api_me_telegram_links"),
    path(
        "api/me/telegram/links/<int:link_id>/",
        views.api_me_telegram_link_delete,
        name="api_me_telegram_link_delete",
    ),
    path("api/me/telegram/bots/", views.api_me_telegram_bots, name="api_me_telegram_bots"),
    path(
        "api/me/telegram/bots/<int:bot_id>/",
        views.api_me_telegram_bot_detail,
        name="api_me_telegram_bot_detail",
    ),
    path(
        "api/me/telegram/bots/<int:bot_id>/test/",
        views.api_me_telegram_bot_test,
        name="api_me_telegram_bot_test",
    ),
    path("api/studio/telegram/bots/", views.api_studio_telegram_bots, name="api_studio_telegram_bots"),
    path(
        "api/studio/telegram/bots/<int:bot_id>/",
        views.api_studio_telegram_bot_detail,
        name="api_studio_telegram_bot_detail",
    ),
]

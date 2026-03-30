"""
Decorators for feature-based access: require_feature('orchestrator') etc.
"""
from functools import wraps
from django.shortcuts import redirect
from django.http import JsonResponse, HttpResponseForbidden
from asgiref.sync import sync_to_async

from core_ui.context_processors import user_can_feature


def async_login_required(view_func):
    """
    Async-view-safe login_required: проверка request.user делается через sync_to_async,
    чтобы не вызывать SynchronousOnlyOperation в async-контексте.
    """
    @wraps(view_func)
    async def _wrapped(request, *args, **kwargs):
        is_authenticated = await sync_to_async(
            lambda r: getattr(r.user, 'is_authenticated', False)
        )(request)
        if not is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return await view_func(request, *args, **kwargs)
    return _wrapped


def async_require_feature(feature, redirect_on_forbidden=False):
    """
    Async-view-safe require_feature: проверки request.user и user_can_feature через sync_to_async.
    Использовать для async views вместе с @async_login_required.
    """
    def decorator(view_func):
        @wraps(view_func)
        async def _wrapped(request, *args, **kwargs):
            is_authenticated = await sync_to_async(
                lambda r: getattr(r.user, 'is_authenticated', False)
            )(request)
            if not is_authenticated:
                if redirect_on_forbidden:
                    return redirect('login')
                return HttpResponseForbidden()
            can_feature = await sync_to_async(
                lambda r: user_can_feature(r.user, feature)
            )(request)
            if not can_feature:
                if redirect_on_forbidden:
                    return redirect('index')
                return JsonResponse({'error': 'Forbidden'}, status=403)
            return await view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def require_feature(feature, redirect_on_forbidden=False):
    """
    Restrict view to users who have permission for `feature`.
    - redirect_on_forbidden=True: redirect to index (for page views).
    - redirect_on_forbidden=False: return 403 / JsonResponse (for API views).
    Must be used after @login_required so request.user is set.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if redirect_on_forbidden:
                    return redirect('login')
                return HttpResponseForbidden()
            if not user_can_feature(request.user, feature):
                if redirect_on_forbidden:
                    return redirect('index')
                return JsonResponse({'error': 'Forbidden'}, status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def require_any_feature(*features, redirect_on_forbidden=False):
    """
    Restrict view to users who have permission for at least one feature.
    """

    normalized_features = [feature for feature in features if feature]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if redirect_on_forbidden:
                    return redirect("login")
                return HttpResponseForbidden()
            if not any(user_can_feature(request.user, feature) for feature in normalized_features):
                if redirect_on_forbidden:
                    return redirect("index")
                return JsonResponse({"error": "Forbidden"}, status=403)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator

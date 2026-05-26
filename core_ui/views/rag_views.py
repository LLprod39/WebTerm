"""
Legacy RAG knowledge-base API endpoints.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.decorators import require_feature
from core_ui.views.runtime import get_rag_engine


@login_required
@require_feature("knowledge_base")
@require_http_methods(["POST"])
def rag_add_api(request):
    """Add text to the RAG knowledge base."""
    try:
        data = json.loads(request.body)
        text = data.get("text", "")
        source = data.get("source", "manual")

        if not text:
            return JsonResponse({"success": False, "error": "Empty text"}, status=400)

        rag = get_rag_engine()
        if not rag.available:
            return JsonResponse({"success": False, "error": "RAG not available"}, status=503)

        doc_id = rag.add_text(text, source, user_id=request.user.id)
        if doc_id is None:
            return JsonResponse({"success": False, "error": "Failed to add document to RAG"}, status=500)

        return JsonResponse({"success": True, "doc_id": doc_id, "message": "Document added successfully"})
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.error(f"Error in rag_add_api: {exc}")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_feature("knowledge_base")
@require_http_methods(["POST"])
def rag_query_api(request):
    """Query the RAG knowledge base."""
    try:
        data = json.loads(request.body)
        query = data.get("query", "")
        n_results = data.get("n_results", 5)

        if not query:
            return JsonResponse({"success": False, "error": "Empty query"}, status=400)

        rag = get_rag_engine()
        if not rag.available:
            return JsonResponse(
                {"success": False, "error": "RAG not available", "documents": [[]], "metadatas": [[]]},
                status=503,
            )

        try:
            results = rag.query(query, n_results, user_id=request.user.id)
            return JsonResponse(
                {
                    "success": True,
                    "documents": results.get("documents", [[]]),
                    "metadatas": results.get("metadatas", [[]]),
                }
            )
        except Exception as exc:
            logger.error(f"Error querying RAG: {exc}")
            return JsonResponse(
                {"success": False, "error": f"Query failed: {str(exc)}", "documents": [[]], "metadatas": [[]]},
                status=500,
            )
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON", "documents": [[]], "metadatas": [[]]},
            status=400,
        )
    except Exception as exc:
        logger.error(f"Error in rag_query_api: {exc}")
        return JsonResponse({"success": False, "error": str(exc), "documents": [[]], "metadatas": [[]]}, status=500)


@login_required
@require_feature("knowledge_base")
@require_http_methods(["POST"])
def rag_reset_api(request):
    """Reset the user's RAG database."""
    try:
        rag = get_rag_engine()
        if not rag.available:
            return JsonResponse({"success": False, "error": "RAG not available"}, status=503)

        try:
            rag.reset_db(user_id=request.user.id)
            return JsonResponse({"success": True, "message": "Database reset successfully"})
        except Exception as exc:
            logger.error(f"Error resetting RAG: {exc}")
            return JsonResponse({"success": False, "error": f"Reset failed: {str(exc)}"}, status=500)
    except Exception as exc:
        logger.error(f"Error in rag_reset_api: {exc}")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_feature("knowledge_base")
@require_http_methods(["POST"])
def rag_delete_api(request):
    """Delete a single RAG document by id."""
    try:
        data = json.loads(request.body) if request.body else {}
        doc_id = data.get("doc_id") or data.get("id")
        if not doc_id:
            return JsonResponse({"success": False, "error": "doc_id required"}, status=400)
        rag = get_rag_engine()
        if not rag.available:
            return JsonResponse({"success": False, "error": "RAG not available"}, status=503)
        removed = rag.delete_document(str(doc_id), user_id=request.user.id)
        if removed:
            return JsonResponse({"success": True, "message": "Document deleted"})
        return JsonResponse({"success": False, "error": "Document not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.error(f"Error in rag_delete_api: {exc}")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@login_required
@require_feature("knowledge_base")
def rag_documents_api(request):
    """Get RAG documents with pagination."""
    try:
        rag = get_rag_engine()
        if not rag.available:
            return JsonResponse({"success": False, "error": "RAG not available", "documents": [], "doc_count": 0})

        limit = int(request.GET.get("limit", 50))
        offset = int(request.GET.get("offset", 0))
        all_documents = rag.get_documents(limit=limit + offset, user_id=request.user.id)
        documents = all_documents[offset : offset + limit]
        total_count = len(all_documents) if offset == 0 else len(all_documents)

        return JsonResponse(
            {
                "success": True,
                "documents": documents,
                "doc_count": total_count,
                "has_more": len(all_documents) > offset + limit,
            }
        )
    except Exception as exc:
        logger.error(f"Error getting documents: {exc}")
        return JsonResponse({"success": False, "error": str(exc), "documents": [], "doc_count": 0})

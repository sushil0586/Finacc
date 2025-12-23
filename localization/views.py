from django.db.models import Max
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status

from .models import Language, LocalizedStringKey, LocalizedStringValue


class LocalizedStringsAPIView(APIView):
    """
    GET /api/localization/strings?lang=en&entity=50&module=invoice

    Fallback:
      1) entity-specific
      2) global (entity_id NULL)
      3) key.default_text
      4) key itself
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        lang_code = (request.query_params.get("lang") or "en").strip()
        module = (request.query_params.get("module") or "").strip()
        entity_param = request.query_params.get("entity")

        entity_id = None
        if entity_param not in (None, "", "null", "None"):
            try:
                entity_id = int(entity_param)
            except ValueError:
                return Response({"detail": "entity must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            lang = Language.objects.get(code=lang_code, is_active=True)
        except Language.DoesNotExist:
            return Response({"detail": f"Language '{lang_code}' not found/active"}, status=status.HTTP_404_NOT_FOUND)

        keys_qs = LocalizedStringKey.objects.filter(is_active=True)
        if module:
            keys_qs = keys_qs.filter(module=module)

        keys = list(keys_qs.values("id", "key", "default_text"))
        if not keys:
            return Response(
                {"language": lang.code, "entity": entity_id, "module": module, "updated_at": None, "strings": {}},
                status=status.HTTP_200_OK,
            )

        key_ids = [k["id"] for k in keys]

        values_qs = LocalizedStringValue.objects.filter(
            string_key_id__in=key_ids,
            language=lang,
            is_approved=True
        ).values("string_key_id", "text", "entity_id")

        global_map = {}
        entity_map = {}

        for row in values_qs:
            if row["entity_id"] is None:
                global_map[row["string_key_id"]] = row["text"]
            else:
                # keep only requested entity override in map
                if entity_id is not None and row["entity_id"] == entity_id:
                    entity_map[row["string_key_id"]] = row["text"]

        strings = {}
        for k in keys:
            kid = k["id"]
            if entity_id is not None and kid in entity_map:
                strings[k["key"]] = entity_map[kid]
            elif kid in global_map:
                strings[k["key"]] = global_map[kid]
            elif k["default_text"]:
                strings[k["key"]] = k["default_text"]
            else:
                strings[k["key"]] = k["key"]

        updated_at = LocalizedStringValue.objects.filter(
            string_key_id__in=key_ids,
            language=lang,
            is_approved=True
        ).aggregate(mx=Max("updated_at"))["mx"]

        return Response(
            {
                "language": lang.code,
                "entity": entity_id,
                "module": module,
                "updated_at": updated_at,
                "strings": strings,
            },
            status=status.HTTP_200_OK,
        )

from __future__ import annotations

from rest_framework import serializers

from vouchers.models import VoucherAttachment


class VoucherAttachmentSerializer(serializers.ModelSerializer):
    file_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()

    class Meta:
        model = VoucherAttachment
        fields = [
            "id",
            "file_name",
            "original_name",
            "content_type",
            "size",
            "file_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_file_name(self, obj: VoucherAttachment) -> str:
        return obj.original_name or obj.file.name.split("/")[-1]

    def get_file_url(self, obj: VoucherAttachment) -> str | None:
        try:
            return obj.file.url if obj.file else None
        except Exception:
            return None

    def get_size(self, obj: VoucherAttachment) -> int:
        try:
            return int(obj.file.size or 0)
        except Exception:
            return 0

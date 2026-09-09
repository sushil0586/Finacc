from rest_framework.exceptions import APIException


class StaleObjectConflict(APIException):
    status_code = 409
    default_code = "stale_object"
    default_detail = "This document changed after you opened it. Reload it before saving again."


def assert_expected_updated_at(instance, expected_updated_at) -> None:
    if expected_updated_at is None:
        return
    if instance.updated_at != expected_updated_at:
        raise StaleObjectConflict({
            "detail": StaleObjectConflict.default_detail,
            "code": StaleObjectConflict.default_code,
            "current_updated_at": instance.updated_at,
        })
